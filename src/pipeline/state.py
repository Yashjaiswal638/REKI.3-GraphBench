"""Typed state schema for the GraphBench pipeline."""
from typing import TypedDict, Annotated
import operator

class BenchState(TypedDict):
    # Task identity
    task_id: str
    task_number: int
    problem_description: str
    dut_header: str
    dut_code: str              # golden RTL

    # Stage outputs
    circuit_type: str           # "CMB" or "SEQ" (Stage0)
    spec: str                   # technical spec JSON (Stage1)
    scenarios: str              # test scenarios JSON (Stage2)
    golden_rules: str           # python rule code (Stage3)
    driver_code: str            # verilog testbench (Stage4)
    checker_code: str           # python checker (Stage5)

    # Simulation
    sim_passed: bool
    sim_output: str
    sim_error: str
    debug_iter: int
    reboot_count: int

    # Evaluation
    eval0_passed: bool          # compiles
    eval1_passed: bool          # golden RTL check
    eval2_passed: bool          # mutant detection
    eval2_mutant_ratio: str     # e.g. "8/10"

    # VCD analysis
    vcd_path: str
    waveform_analysis: str      # LLM diagnosis from waveforms

    # Flow control
    errors: Annotated[list, operator.add]