"""Tool layer: the 15 pipeline operations exposed as LangChain tools.

State handling is LangGraph-native: tools receive the graph state via
InjectedState (the LLM still sends `{}` — injected params are hidden from the
schema) and write results back into the LangGraph channels by returning a
`Command(update=...)` plus a ToolMessage status.

In this langgraph version ToolRuntime.state is a *snapshot* (mutations do not
propagate), so Command.update is the supported write-back mechanism.

Each tool: guard → call the AutoBench node function from reki3.core.graph →
return Command(update + status ToolMessage). Guard refusals raise
GuardRefusal, which ToolNode (via handle_guard_error) converts into
error-status ToolMessages the agent can read and react to.
"""
import os
import json
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool, ToolException
from langgraph.prebuilt import InjectedState
from langgraph.prebuilt.tool_node import ToolRuntime
from langgraph.types import Command

from reki3.core import graph as nodes

MAX_DEBUG = 3
MAX_REBOOTS = 2

# AutoBench analyze.py: LOOSE_FACTOR = 0.8 ("the R in paper") — Eval2/Eval2b
# pass when the verdict-match ratio reaches R.
LOOSE_FACTOR = 0.8

# stage4b sends very large prompts through the raw OpenAI SDK, which has no
# explicit timeout (SDK default 600s + retries can block ~30 min). Known hang
# point for long SEQ problems (fsm_serialdata, fsm_ps2data family).
STAGE4B_TIMEOUT_S = 300
# vcd_node (diagnose) calls ChatOpenAI with request_timeout=300 but langchain
# may retry; mux9to1v showed it can hang too.
DIAGNOSE_TIMEOUT_S = 300

_State = Annotated[dict, InjectedState]
_Runtime = Annotated[ToolRuntime, InjectedState]


class GuardRefusal(ToolException):
    """Prerequisite-guard violation.

    Subclasses ToolException (handled natively by older langgraph versions);
    newer ToolNode versions need the custom handle_tool_errors callable
    passed in reki3/agent/graph.py.
    """


def _refused(msg: str):
    raise GuardRefusal(msg)


def handle_guard_error(e: Exception) -> str:
    """ToolNode handle_tool_errors callable: convert guard refusals to
    error-content ToolMessages; re-raise anything else."""
    if isinstance(e, GuardRefusal):
        return str(e)
    raise e


def _done(tool_runtime, update: dict, msg: str) -> Command:
    """Write-back: state update as Command.update (merged into channels) plus
    the one-line status as a ToolMessage for the LLM (messages go inside
    update — Command itself only takes graph/update/resume/goto)."""
    upd = {k: v for k, v in update.items() if v is not None}
    upd["messages"] = [ToolMessage(content=msg, tool_call_id=tool_runtime.tool_call_id,
                                   status="success")]
    return Command(update=upd)


def _compile_error(state) -> bool:
    err = (state.get("sim_error") or "").lower()
    return any(m in err for m in (
        "syntax error", "unable to bind", "undeclared", "undefined macro",
        "invalid module", "parse error", "expecting", "compilation error"))


def _is_checker_error(state) -> bool:
    err = (state.get("sim_error") or "").lower()
    return any(m in err for m in (
        "python checker", "traceback", "typeerror", "attributeerror",
        "indexerror", "keyerror", "nameerror"))


def _run_with_timeout(state, fn, timeout_s):
    """Run a node function in a daemon thread; return (update_dict, completed).

    A hung LLM call leaves a daemon thread blocked in the background but the
    agent loop moves on."""
    import threading
    box = {}

    def target():
        try:
            box["result"] = fn(state)
        except Exception as e:
            box["error"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        return None, False
    if "error" in box:
        raise box["error"]
    return box["result"], True


# ---------------------------------------------------------------------------
# Eval2b: verdict parity against GPT-generated RTL (AutoBench TaskTBeval,
# mode="gptgen"). Data: data/HDLBits/HDLBits_data_RTL.jsonl
# ---------------------------------------------------------------------------

_GPTGEN_LOOKUP = {}
_GPTGEN_LOADED = False


def _load_gptgen():
    global _GPTGEN_LOOKUP, _GPTGEN_LOADED
    if _GPTGEN_LOADED:
        return
    _GPTGEN_LOADED = True
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        "..", "data", "HDLBits", "HDLBits_data_RTL.jsonl")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = json.loads(line)
                _GPTGEN_LOOKUP[m["task_id"]] = m.get("gptgen_RTL", [])


def _golden_tb_verdict(gold_dir, task_id, rtl_code, golden_tb):
    os.makedirs(gold_dir, exist_ok=True)
    with open(os.path.join(gold_dir, f"{task_id}.v"), "w") as f:
        f.write(rtl_code)
    with open(os.path.join(gold_dir, f"{task_id}_tb.v"), "w") as f:
        f.write(golden_tb)
    gold_result = nodes.iverilog_call_and_save(gold_dir, silent=True, timeout=30)
    if gold_result[0] and gold_result[4]:
        vvp_out = gold_result[4].out if hasattr(gold_result[4], "out") else str(gold_result[4])
        return True, ("Mismatches: 0 in" in vvp_out or "All test cases passed" in vvp_out)
    return False, False


def _generated_tb_verdict(gen_dir, task_id, rtl_code, driver_code, checker_code):
    os.makedirs(gen_dir, exist_ok=True)
    with open(os.path.join(gen_dir, f"{task_id}.v"), "w") as f:
        f.write(rtl_code)
    with open(os.path.join(gen_dir, f"{task_id}_tb.v"), "w") as f:
        f.write(driver_code)
    gen_result = nodes.iverilog_call_and_save(gen_dir, silent=True, timeout=30)
    if gen_result[0] and checker_code:
        with open(os.path.join(gen_dir, f"{task_id}_tb.py"), "w") as f:
            f.write(checker_code)
        py_result = nodes.python_call_and_save(
            os.path.join(gen_dir, f"{task_id}_tb.py"), silent=True, timeout=30)
        checker_out = py_result[1].out.strip() if py_result[1] else ""
        return checker_out == "[]"
    return bool(gen_result[0])


def _run_eval2b(state) -> dict:
    task_id = state.get("task_id")
    if not state.get("sim_passed"):
        return {"eval2b_passed": False, "eval2b_ratio": "N/A (Eval1 failed)"}

    _load_gptgen()
    gptgen_list = _GPTGEN_LOOKUP.get(task_id, [])
    nodes._load_eval_data()
    golden_tb = nodes._GOLDEN_TB_LOOKUP.get(task_id, "")
    if not gptgen_list:
        return {"eval2b_passed": False, "eval2b_ratio": "N/A (no gptgen RTL)"}
    if not golden_tb:
        return {"eval2b_passed": False, "eval2b_ratio": "N/A (no golden TB)"}

    work_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                            "..", "runs", task_id, "eval2b") + os.sep
    matched = 0
    evaluated = 0
    for idx, rtl_code in enumerate(gptgen_list):
        try:
            gold_valid, gold_pass = _golden_tb_verdict(
                os.path.join(work_dir, f"golden_{idx}"), task_id, rtl_code, golden_tb)
        except Exception:
            gold_valid = False
        if not gold_valid:
            continue
        try:
            gen_pass = _generated_tb_verdict(
                os.path.join(work_dir, f"gen_{idx}"), task_id, rtl_code,
                state["driver_code"], state.get("checker_code"))
        except Exception:
            gen_pass = False
        if gold_pass == gen_pass:
            matched += 1
        evaluated += 1

    if evaluated == 0:
        return {"eval2b_passed": False, "eval2b_ratio": "0/0 (no valid golden verdicts)"}
    return {"eval2b_passed": matched / evaluated >= LOOSE_FACTOR,
            "eval2b_ratio": f"{matched}/{evaluated}"}


def run_full_eval(state, tool_runtime) -> Command:
    """Eval0/1/2 + Eval2b; returns a Command that updates the channels.

    Set REKI3_SKIP_EVAL2B=1 to skip Eval2b (used for pass@k sampling where
    Eval2b is not part of the headline metrics and doubles eval runtime)."""
    merged = dict(state)
    merged.update({k: v for k, v in nodes.eval_node(state).items() if v is not None})
    if os.environ.get("REKI3_SKIP_EVAL2B", "0") != "1":
        merged.update({k: v for k, v in _run_eval2b(state).items() if v is not None})
    msg = (f"eval: sim={merged.get('sim_passed')}, eval0={merged.get('eval0_passed')}, "
           f"eval1={merged.get('eval1_passed')}, eval2={merged.get('eval2_passed')} "
           f"({merged.get('eval2_mutant_ratio')}), "
           f"eval2b={merged.get('eval2b_passed')} ({merged.get('eval2b_ratio')}) — RUN COMPLETE")
    return _done(tool_runtime, {k: merged.get(k) for k in
                 ("eval0_passed", "eval1_passed", "eval2_passed",
                  "eval2_mutant_ratio", "eval2b_passed", "eval2b_ratio")}, msg)


# ---------------------------------------------------------------------------
# The 15 tools
# ---------------------------------------------------------------------------

@tool
def classify(state: _State, tool_runtime: _Runtime) -> str:
    """Determine if the circuit is combinational (CMB) or sequential (SEQ). Call FIRST, before any other tool."""
    if state.get("circuit_type"):
        return _refused(f"circuit already classified as {state['circuit_type']}")
    return _done(tool_runtime, nodes.classify_node(state),
                 f"classify: circuit_type = {state.get('circuit_type')}")


@tool
def spec(state: _State, tool_runtime: _Runtime) -> str:
    """Generate the JSON technical specification of the DUT. Call after classify."""
    if not state.get("circuit_type"):
        return _refused("classify must run first")
    if state.get("spec"):
        return _refused("spec already generated")
    return _done(tool_runtime, nodes.spec_node(state), "spec: generated")


@tool
def scenarios(state: _State, tool_runtime: _Runtime) -> str:
    """Plan test scenarios (input stimuli only, no expected outputs). Call after spec."""
    if not state.get("spec"):
        return _refused("spec must run first")
    if state.get("scenarios"):
        return _refused("scenarios already generated")
    return _done(tool_runtime, nodes.scenarios_node(state), "scenarios: generated")


@tool
def rules(state: _State, tool_runtime: _Runtime) -> str:
    """Write Python golden rules (reference behavior) for the DUT. Call after scenarios."""
    if not state.get("scenarios"):
        return _refused("scenarios must run first")
    if state.get("golden_rules"):
        return _refused("rules already generated")
    return _done(tool_runtime, nodes.rules_node(state), "rules: generated")


@tool
def driver_cmb(state: _State, tool_runtime: _Runtime) -> str:
    """Generate the Verilog testbench for a COMBINATIONAL circuit (no clock). Only valid when circuit_type == CMB. Call after rules."""
    if state.get("circuit_type") != "CMB":
        return _refused(f"requires circuit_type=CMB (currently {state.get('circuit_type')})")
    if not state.get("scenarios"):
        return _refused("scenarios must run first")
    if state.get("driver_code"):
        return _refused("driver already exists; use reboot to regenerate")
    return _done(tool_runtime, nodes.driver_cmb_node(state),
                 "driver_cmb: Verilog testbench generated")


@tool
def driver_seq(state: _State, tool_runtime: _Runtime) -> str:
    """Generate the Verilog testbench skeleton for a SEQUENTIAL circuit (has clock). Only valid when circuit_type == SEQ. Call after rules."""
    if state.get("circuit_type") != "SEQ":
        return _refused(f"requires circuit_type=SEQ (currently {state.get('circuit_type')})")
    if not state.get("scenarios"):
        return _refused("scenarios must run first")
    if state.get("driver_code"):
        return _refused("driver already exists; use reboot to regenerate")
    return _done(tool_runtime, nodes.driver_seq_node(state),
                 "driver_seq: Verilog testbench generated")


@tool
def checklist(state: _State, tool_runtime: _Runtime) -> str:
    """Verify all planned scenarios are covered by the driver (regex pre-check, LLM fallback). Call after driver generation."""
    if not state.get("driver_code"):
        return _refused("driver must exist first")
    return _done(tool_runtime, nodes.checklist_node(state),
                 "checklist: scenarios verified (driver updated if gaps found)")


@tool
def checker_cmb(state: _State, tool_runtime: _Runtime) -> str:
    """Generate the Python checker for a COMBINATIONAL circuit. Only valid when circuit_type == CMB. Call after checklist."""
    if state.get("circuit_type") != "CMB":
        return _refused(f"requires circuit_type=CMB (currently {state.get('circuit_type')})")
    if not state.get("driver_code"):
        return _refused("driver must exist first")
    if not state.get("golden_rules"):
        return _refused("rules must run first")
    if state.get("checker_code"):
        return _refused("checker already exists")
    return _done(tool_runtime, nodes.checker_cmb_node(state),
                 "checker_cmb: Python checker generated")


@tool
def stage4b(state: _State, tool_runtime: _Runtime) -> str:
    """Insert $fdisplay instrumentation into a SEQUENTIAL driver so it logs signal values to TBout.txt. Only valid for SEQ circuits, after driver_seq."""
    if state.get("circuit_type") != "SEQ":
        return _refused(f"requires circuit_type=SEQ (currently {state.get('circuit_type')})")
    if not state.get("driver_code"):
        return _refused("driver must exist first")
    update, ok = _run_with_timeout(state, nodes.stage4b_node, STAGE4B_TIMEOUT_S)
    if not ok:
        return (f"stage4b: TIMED OUT after {STAGE4B_TIMEOUT_S}s — the prompt is too "
                "large for the model. The driver already logs some signals, so you "
                "may try simulate directly without stage4b.")
    return _done(tool_runtime, update, "stage4b: $fdisplay inserted into SEQ driver")


@tool
def checker_seq(state: _State, tool_runtime: _Runtime) -> str:
    """Generate the Python GoldenDUT checker for a SEQUENTIAL circuit. Only valid when circuit_type == SEQ. Call after stage4b."""
    if state.get("circuit_type") != "SEQ":
        return _refused(f"requires circuit_type=SEQ (currently {state.get('circuit_type')})")
    if not state.get("driver_code"):
        return _refused("driver must exist first")
    if not state.get("golden_rules"):
        return _refused("rules must run first")
    if state.get("checker_code"):
        return _refused("checker already exists")
    return _done(tool_runtime, nodes.checker_seq_node(state),
                 "checker_seq: Python GoldenDUT checker generated")


@tool
def simulate(state: _State, tool_runtime: _Runtime) -> str:
    """Compile the driver with iverilog, simulate with vvp, and run the Python checker. Call after driver AND checker exist, and again after every debug/reboot fix."""
    if not state.get("driver_code"):
        return _refused("driver must exist first")
    if not state.get("checker_code"):
        return _refused("checker must exist first")
    update = nodes.simulation_node(state)
    if state.get("sim_passed") or update.get("sim_passed"):
        return _done(tool_runtime, update, "simulate: PASSED")
    return _done(tool_runtime, update,
                 f"simulate: FAILED — {((state.get('sim_error') or update.get('sim_error') or ''))[:200]}")


@tool
def debug(state: _State, tool_runtime: _Runtime) -> str:
    """Fix the broken Verilog driver or Python checker using the compile/run error message. Call after a failed simulate. Max 3 attempts; after TWO failed attempts analyze_waveform is REQUIRED before another debug (unless the error is a compile error)."""
    if state.get("sim_passed"):
        return _refused("no failure to fix (simulation passed)")
    if not state.get("sim_error"):
        return _refused("no sim_error recorded; run simulate first")
    if state.get("debug_iter", 0) >= MAX_DEBUG:
        return _refused(f"debug budget exhausted ({MAX_DEBUG}); call eval")
    if (state.get("debug_iter", 0) >= 2
            and not state.get("waveform_analysis")
            and not _compile_error(state)):
        return _refused("debug failed twice with no diagnosis — run analyze_waveform first to find the root cause")
    update = nodes.debug_node(state)
    merged = dict(state); merged.update(update)
    return _done(tool_runtime, update,
                 f"debug: code fixed (attempt {merged.get('debug_iter')}); re-run simulate")


@tool
def analyze_waveform(state: _State, tool_runtime: _Runtime) -> str:
    """Analyze the VCD waveform / TBout signal data after a failed simulation to diagnose the ROOT CAUSE. Use BEFORE debug when signals exist (skip for pure compile errors)."""
    if state.get("sim_passed"):
        return _refused("no failure to diagnose (simulation passed)")
    if not state.get("sim_error"):
        return _refused("no sim_error recorded; run simulate first")
    if _compile_error(state):
        return _refused("compile error: no waveform to analyze; use debug directly")
    update, ok = _run_with_timeout(state, nodes.vcd_node, DIAGNOSE_TIMEOUT_S)
    if not ok:
        return (f"analyze_waveform: TIMED OUT after {DIAGNOSE_TIMEOUT_S}s — "
                "proceed with debug using sim_error instead.")
    merged = dict(state); merged.update(update)
    return _done(tool_runtime, update,
                 f"analyze_waveform: diagnosis — {(merged.get('waveform_analysis') or '')[:200]}")


@tool
def reboot(state: _State, tool_runtime: _Runtime) -> str:
    """Regenerate the driver from scratch (CMB or SEQ based on circuit_type) and reset debug_iter. Use after TWO failed debug attempts on the same failure. Max 2 reboots; after two failed debugs analyze_waveform is REQUIRED before rebooting (unless compile error)."""
    if state.get("debug_iter", 0) < 1:
        return _refused("debug must be attempted before reboot")
    if state.get("reboot_count", 0) >= MAX_REBOOTS:
        return _refused(f"reboot budget exhausted ({MAX_REBOOTS}); call eval")
    if (state.get("debug_iter", 0) >= 2
            and not state.get("waveform_analysis")
            and not _compile_error(state)):
        return _refused("debug failed twice with no diagnosis — run analyze_waveform first to find the root cause")
    upd = {k: v for k, v in nodes.reboot_node(state).items() if v is not None}
    merged = dict(state); merged.update(upd)
    msg = (f"reboot: driver regenerated from scratch (reboot {merged.get('reboot_count')}); "
           "re-run simulate")
    if _is_checker_error(state) and state.get("golden_rules"):
        ct = state.get("circuit_type")
        if ct == "SEQ":
            upd.update({k: v for k, v in nodes.checker_seq_node(state).items() if v is not None})
        elif ct == "CMB":
            upd.update({k: v for k, v in nodes.checker_cmb_node(state).items() if v is not None})
        msg += "; Python checker was ALSO regenerated (the failure was in the checker)"
    return _done(tool_runtime, upd, msg)


@tool("eval")
def evaluate(state: _State, tool_runtime: _Runtime) -> str:
    """Run Eval0 (compiles), Eval1 (golden RTL pass), Eval2 (mutant detection vs golden TB) and Eval2b (GPT-generated RTL detection). Call when simulation passes OR retry budgets are exhausted. This completes the run."""
    if state.get("eval2_mutant_ratio"):
        return _refused("eval already ran")
    if (not state.get("sim_passed")
            and state.get("debug_iter", 0) < MAX_DEBUG
            and state.get("reboot_count", 0) < MAX_REBOOTS):
        return _refused("retry budgets not exhausted; fix the failure first")
    return run_full_eval(state, tool_runtime)


TOOL_LIST = [classify, spec, scenarios, rules, driver_cmb, driver_seq,
             checklist, checker_cmb, stage4b, checker_seq, simulate,
             debug, analyze_waveform, reboot, evaluate]
