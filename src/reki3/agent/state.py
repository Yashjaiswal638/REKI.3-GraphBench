"""Typed state for the LangGraph agent: BenchState fields + message history.

Same fields as pipeline/state.py:BenchState, plus a `messages` channel that
LangGraph uses for agent <-> ToolNode routing. `errors` is kept for schema
compatibility but is never written by the current nodes.
"""
from typing import TypedDict, Annotated
import operator


class AgentState(TypedDict):
    # Task identity
    task_id: str
    task_number: int
    problem_description: str
    dut_header: str
    dut_code: str              # golden RTL

    # Stage outputs
    circuit_type: str           # "CMB" or "SEQ"
    spec: str
    scenarios: str
    golden_rules: str
    driver_code: str
    checker_code: str

    # Simulation
    sim_passed: bool
    sim_output: str
    sim_error: str
    debug_iter: int
    reboot_count: int

    # Evaluation
    eval0_passed: bool
    eval1_passed: bool
    eval2_passed: bool
    eval2_mutant_ratio: str
    eval2b_passed: bool        # Eval2b: verdict parity on GPT-generated RTL
    eval2b_ratio: str

    # VCD analysis
    vcd_path: str
    waveform_analysis: str

    # Agent conversation (LangGraph routing channel)
    messages: Annotated[list, operator.add]

    # Accumulated errors
    errors: Annotated[list, operator.add]


# Plain-overwrite fields echoed back to graph state by the agent node each
# turn. Excludes the Annotated accumulator channels (messages, errors).
WRITEBACK_FIELDS = (
    "task_id", "task_number", "problem_description", "dut_header", "dut_code",
    "circuit_type", "spec", "scenarios", "golden_rules", "driver_code",
    "checker_code", "sim_passed", "sim_output", "sim_error", "debug_iter",
    "reboot_count", "eval0_passed", "eval1_passed", "eval2_passed",
    "eval2_mutant_ratio", "eval2b_passed", "eval2b_ratio",
    "vcd_path", "waveform_analysis",
)
