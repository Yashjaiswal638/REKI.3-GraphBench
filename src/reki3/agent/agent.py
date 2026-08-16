"""The LLM agent node and the finalize safety net.

agent_node: builds a compact state summary, asks the LLM (with bound tools)
which single operation to run next, and returns the tool-call message. The
typed state lives in the LangGraph channels — tools read it via InjectedState
and write back via Command.update.

finalize_node: guarantees eval runs before the graph ends, mirroring the
old Python-loop agent's "LLM said DONE -> run eval first" behavior.
"""
import os

from langchain_core.messages import HumanMessage, SystemMessage, trim_messages

from reki3.core.graph import get_llm, eval_node
from .tools import TOOL_LIST, MAX_DEBUG, MAX_REBOOTS, _run_eval2b

AGENT_SYSTEM_PROMPT = """You are a hardware verification agent that generates Verilog testbenches for RTL circuits (DUT).

Typical workflow: classify -> spec -> scenarios -> rules -> driver_cmb|driver_seq -> checklist -> [stage4b if SEQ] -> checker_cmb|checker_seq -> simulate.
If simulation fails: analyze_waveform (for non-compile errors) -> debug -> simulate again. If debug keeps failing: reboot -> simulate.
When simulation passes or retry budgets are exhausted: eval. After eval the run is complete.

Rules:
- Call exactly ONE tool per step. Always respond with a tool call, never plain text.
- Respect each tool's prerequisites; if a tool reports an error, pick a different valid tool.
- If several of your tool calls were refused in a row without progress, call eval instead of retrying them.
- After debug, reboot, or any code change, you MUST call simulate again to verify.
- If two consecutive debug attempts fail, run analyze_waveform (unless the error is a compile error), then debug once more with the diagnosis; if that still fails, reboot.
- You MUST call eval when simulation passes or when debug/reboot budgets are exhausted."""


def _status(v):
    return "ready" if v else "MISSING"


def _build_state_summary(s, msgs) -> str:
    lines = [
        f"task_id: {s.get('task_id')}",
        f"circuit_type: {s.get('circuit_type') or 'unknown (call classify)'}",
        f"spec: {_status(s.get('spec'))}",
        f"scenarios: {_status(s.get('scenarios'))}",
        f"golden_rules: {_status(s.get('golden_rules'))}",
        f"driver_code: {_status(s.get('driver_code'))}",
        f"checker_code: {_status(s.get('checker_code'))}",
        f"sim_passed: {s.get('sim_passed')}",
        f"sim_error: {(s.get('sim_error') or '')[:200] or 'none'}",
        f"debug_iter: {s.get('debug_iter', 0)}/{MAX_DEBUG}, reboot_count: {s.get('reboot_count', 0)}/{MAX_REBOOTS}",
    ]
    if s.get("eval2_mutant_ratio"):
        lines.append(f"eval: done ({s.get('eval2_mutant_ratio')})")
    else:
        lines.append("eval: not run")
    if (s.get("driver_code") and s.get("checker_code")
            and not s.get("sim_passed") and not s.get("sim_error")):
        lines.append("NOTE: driver and checker are ready — call simulate.")
    if s.get("debug_iter", 0) >= MAX_DEBUG and not s.get("eval2_mutant_ratio"):
        lines.append(f"NOTE: debug budget exhausted — call eval.")
    if s.get("reboot_count", 0) >= MAX_REBOOTS and not s.get("eval2_mutant_ratio"):
        lines.append(f"NOTE: reboot budget exhausted — call eval.")
    if (s.get("debug_iter", 0) >= 2 and not s.get("sim_passed")
            and s.get("reboot_count", 0) < MAX_REBOOTS
            and not s.get("eval2_mutant_ratio")):
        lines.append(f"NOTE: debug failed {s.get('debug_iter')} times — prefer reboot over another debug.")
    if (s.get("debug_iter", 0) >= 2 and not s.get("sim_passed")
            and not s.get("waveform_analysis")
            and not s.get("eval2_mutant_ratio")):
        lines.append("NOTE: debug failed twice — consider analyze_waveform to find the root cause before another debug.")
    if msgs:
        last = msgs[-1]
        if getattr(last, "type", "") == "tool":
            lines.append(f"last tool result: {str(last.content)[:200]}")
    return "Current state:\n" + "\n".join(lines)


def agent_node(state: dict) -> dict:
    if state.get("eval2_mutant_ratio"):
        return {}
    msgs = list(state.get("messages") or [])
    # Token-based windowing (LangChain) instead of a fixed message count.
    # NOTE: no start_on="human" — the channel contains only AI/Tool messages
    # (the state-summary HumanMessage is added below), and trim_messages
    # returns [] when it cannot find the start anchor.
    msgs = trim_messages(
        msgs,
        max_tokens=4000,
        token_counter=len,
        strategy="last",
        include_system=False,
    )
    llm = get_llm().bind_tools(TOOL_LIST)
    response = llm.invoke(
        [SystemMessage(content=AGENT_SYSTEM_PROMPT)]
        + msgs
        + [HumanMessage(content=_build_state_summary(state, msgs))]
    )
    return {"messages": [response]}


def finalize_node(state: dict) -> dict:
    """Safety net: run the full eval (Eval0/1/2 + Eval2b) if the LLM stopped
    without it (cheap when sim failed — eval_node returns immediately)."""
    if state.get("eval2_mutant_ratio"):
        return {}
    upd = {k: v for k, v in eval_node(state).items() if v is not None}
    if os.environ.get("REKI3_SKIP_EVAL2B", "0") != "1":
        upd.update({k: v for k, v in _run_eval2b(state).items() if v is not None})
    return upd


def route_after_agent(state: dict) -> str:
    msgs = state.get("messages") or []
    last = msgs[-1] if msgs else None
    if getattr(last, "tool_calls", None):
        # Refusal-loop safety: if the agent keeps hitting refused tools
        # (3+ error ToolMessages in the last 8), stop and finalize —
        # eval records the failure instead of burning the recursion budget.
        recent = msgs[-8:]
        if sum(1 for m in recent if getattr(m, "status", "") == "error") >= 3:
            return "finalize"
        return "tools"
    return "finalize"
