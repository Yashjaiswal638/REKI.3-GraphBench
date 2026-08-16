"""LangGraph graph for the REKI.3 agent.

    START -> agent (LLM picks one tool)
                |  tool call            |  no tool call
                v                       v
              tools  ------------>   finalize (guarantees eval) -> END
                |
                └-----> agent

The LLM decides the next operation; LangGraph owns state, message routing and
the recursion budget; tool guards enforce prerequisites and retry limits.

State is LangGraph-native: the typed channels ARE the state — tools read it
via InjectedState and write back via Command.update.
"""
import os
from pathlib import Path
import json

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

from .state import AgentState, WRITEBACK_FIELDS
from .tools import TOOL_LIST, handle_guard_error
from .agent import agent_node, finalize_node, route_after_agent


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("agent", agent_node)
    g.add_node("tools", ToolNode(TOOL_LIST, handle_tool_errors=handle_guard_error))
    g.add_node("finalize", finalize_node)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route_after_agent,
                            {"tools": "tools", "finalize": "finalize"})
    g.add_edge("tools", "agent")
    g.add_edge("finalize", END)
    return g.compile()


def agent_loop(initial_state, max_steps=30):
    """Run the LangGraph agent on one problem."""
    graph = build_graph()
    out = graph.invoke(
        {**{k: initial_state.get(k) for k in WRITEBACK_FIELDS}, "messages": []},
        config={"recursion_limit": max(30, max_steps * 2)},
    )

    # Execution trace (tool sequence) for reproducibility
    trace = []
    for step, m in enumerate(out.get("messages") or []):
        for tc in getattr(m, "tool_calls", None) or []:
            trace.append({"step": step, "tool": tc.get("name")})
    try:
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "..")
        run_dir = Path(root) / "runs" / str(out.get("task_id", "unknown"))
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "trace.json").write_text(json.dumps(trace, indent=2))
    except Exception:
        pass

    return out
