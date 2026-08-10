"""Tool definitions — wrap each graph node as an agent tool."""
from pipeline.graph import (
    classify_node, spec_node, scenarios_node, rules_node,
    driver_cmb_node, checklist_node, checker_cmb_node,
    driver_seq_node, stage4b_node, checker_seq_node,
    simulation_node, debug_node, reboot_node, eval_node,
)

TOOLS = {
    "classify": {
        "fn": classify_node,
        "desc": "Determine if circuit is combinational (CMB) or sequential (SEQ). Call FIRST."
    },
    "spec": {
        "fn": spec_node,
        "desc": "Generate JSON technical specification. Call after classify."
    },
    "scenarios": {
        "fn": scenarios_node,
        "desc": "Plan test scenarios (input stimuli only, no expected outputs). Needs spec."
    },
    "rules": {
        "fn": rules_node,
        "desc": "Write Python reference code for ideal circuit behavior. Call after scenarios."
    },
    "driver_cmb": {
        "fn": driver_cmb_node,
        "desc": "Generate Verilog testbench for COMBINATIONAL circuits (no clock). Call after rules."
    },
    "driver_seq": {
        "fn": driver_seq_node,
        "desc": "Generate Verilog testbench for SEQUENTIAL circuits (has clock). Call after rules."
    },
    "checklist": {
        "fn": checklist_node,
        "desc": "Verify all planned scenarios are covered in the generated driver. Call after driver."
    },
    "checker_cmb": {
        "fn": checker_cmb_node,
        "desc": "Generate Python checker for COMBINATIONAL circuits. Call after checklist."
    },
    "stage4b": {
        "fn": stage4b_node,
        "desc": "Insert $fdisplay after every input change in SEQ driver. SEQ only."
    },
    "checker_seq": {
        "fn": checker_seq_node,
        "desc": "Generate Python GoldenDUT checker for SEQUENTIAL circuits. Call after stage4b."
    },
    "simulate": {
        "fn": simulation_node,
        "desc": "Run iverilog + python checker. Returns sim_passed and sim_error."
    },
    "debug": {
        "fn": debug_node,
        "desc": "Fix broken Verilog using compiler error. Call when simulate fails."
    },
    "reboot": {
        "fn": reboot_node,
        "desc": "Regenerate driver from scratch. Use after debug fails twice."
    },
    "eval": {
        "fn": eval_node,
        "desc": "Run Eval0/1/2 quality checks. Call LAST after simulation passes or gives up."
    },
}
