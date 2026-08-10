"""StateGraph definition for GraphBench pipeline."""
import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # src/
from iverilog_call import iverilog_call_and_save
from python_call import python_call_and_save
from langgraph.graph import StateGraph, START, END
from pipeline.state import BenchState
from LLM_call import extract_code, llm_call as raw_llm_call
from pipeline.verilog_utils import (
    given_TB,
    fdisplay_code_gen,
    pychecker_CMB_TB_standardization,
    pychecker_SEQ_TB_standardization,
    header_to_SignalTxt_template,
    SignalTxt_to_dictlist,
    signal_dictlist_template,
    circuit_type_by_code,
)
from pipeline.prompts import *
from langchain_openai import ChatOpenAI
import json as json_module

SIGNALTEMP_PLACEHOLDER_1 = "/* SIGNAL TEMPLATE 1 */"
SIGNALTEMP_PLACEHOLDER_1A = "/* SIGNAL TEMPLATE 1A */"
SIGNALTEMP_PLACEHOLDER_1B = "/* SIGNAL TEMPLATE 1B */"

# Pre-load mutant + golden TB lookup (built once at import, used by eval_node)
_MUTANT_LOOKUP = {}
_GOLDEN_TB_LOOKUP = {}
_DATA_LOADED = False

def _load_eval_data():
    global _MUTANT_LOOKUP, _GOLDEN_TB_LOOKUP, _DATA_LOADED
    if _DATA_LOADED:
        return
    _DATA_LOADED = True
    # Load mutants
    mutant_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data", "HDLBits", "HDLBits_data_mutants.jsonl")
    if os.path.exists(mutant_path):
        with open(mutant_path) as f:
            for line in f:
                m = json.loads(line)
                _MUTANT_LOOKUP[m["task_id"]] = m.get("mutants", [])
    # Load golden TBs from main dataset
    data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data", "HDLBits", "HDLBits_data.jsonl")
    if os.path.exists(data_path):
        with open(data_path) as f:
            for line in f:
                d = json.loads(line)
                _GOLDEN_TB_LOOKUP[d["task_id"]] = d.get("testbench", "")

def get_llm():
    key_path = "../config/key_API.json"
    with open(key_path) as f:
        api_key = json_module.load(f)["OPENAI_API_KEY"]
    return ChatOpenAI(
        model="deepseek-coder",
        api_key=api_key,
        base_url="https://api.deepseek.com",
        temperature=0,
        request_timeout=300  # 5 min per LLM call
    )


# ═══════════════════════════════════════════════════
# Node Functions
# ═══════════════════════════════════════════════════

def classify_node(state: BenchState) -> dict:
    """Stage 0: Classify circuit as CMB or SEQ."""
    task_id = state["task_id"]
    print(f"[{task_id}] Stage 0: Classifying...")
    prompt = CLASSIFY_PROMPT.format(
        problem_description=state["problem_description"],
        dut_header=state["dut_header"]
    )
    llm = get_llm()
    response = llm.invoke(prompt)
    code = extract_code(response.content, "verilog")[-1] if extract_code(response.content, "verilog") else response.content
    circuit_type = circuit_type_by_code(code)
    print(f"[{task_id}] Circuit type: {circuit_type}")
    return {"circuit_type": circuit_type}


# def spec_node(state: BenchState) -> dict:
#     task_id = state["task_id"]
#     print(f"[{task_id}] Stage 1: Generating spec...")
#     prompt = SPEC_PROMPT.format(
#         problem_description=state["problem_description"],
#         dut_header=state["dut_header"]
#     )
#     response, info = llm_call(
#         [{"role": "user", "content": prompt}],
#         model="deepseek-coder",
#         api_key_path="../config/key_API.json",
#         base_url="https://api.deepseek.com"
#     )
#     return {"spec": response}

def spec_node(state: BenchState) -> dict:
    task_id = state["task_id"]
    print(f"[{task_id}] Stage 1: Generating spec...")

    prompt = SPEC_PROMPT.format(
        problem_description=state["problem_description"],
        dut_header=state["dut_header"]
    )

    llm = get_llm()
    response = llm.invoke(prompt)

    return {"spec": response.content}


def scenarios_node(state: BenchState) -> dict:
    task_id = state["task_id"]
    print(f"[{task_id}] Stage 2: Planning scenarios...")
    prompt = SCENARIOS_PROMPT.format(
        problem_description=state["problem_description"],
        spec=state["spec"],
        dut_header=state["dut_header"]
    )
    llm = get_llm()
    response = llm.invoke(prompt)
    return {"scenarios": response.content}


def rules_node(state: BenchState) -> dict:
    task_id = state["task_id"]
    print(f"[{task_id}] Stage 3: Generating golden rules...")
    prompt = RULES_PROMPT.format(
        problem_description=state["problem_description"],
        spec=state["spec"],
        dut_header=state["dut_header"],
        scenarios=state["scenarios"]
    )
    llm = get_llm()
    response = llm.invoke(prompt)
    return {"golden_rules": response.content}


# ── CMB Path ──

def driver_cmb_node(state: BenchState) -> dict:
    """Stage 4 CMB: Generate Verilog driver testbench."""
    task_id = state["task_id"]
    print(f"[{task_id}] Stage 4 (CMB): Generating driver...")
    header = state["dut_header"]

    template_1 = header_to_SignalTxt_template(header, signal_value=r"%d")
    template_1a = header_to_SignalTxt_template(header, "1a", signal_value=r"%d")
    template_1b = header_to_SignalTxt_template(header, "1b", signal_value=r"%d")

    txt1 = (STAGE4_TXT1
            .replace(SIGNALTEMP_PLACEHOLDER_1, template_1)
            .replace(SIGNALTEMP_PLACEHOLDER_1A, template_1a)
            .replace(SIGNALTEMP_PLACEHOLDER_1B, template_1b))
    txt2 = (STAGE4_TXT2
            .replace(SIGNALTEMP_PLACEHOLDER_1, template_1)
            .replace(SIGNALTEMP_PLACEHOLDER_1A, template_1a)
            .replace(SIGNALTEMP_PLACEHOLDER_1B, template_1b))

    prompt = txt1 + "\n" + header + "\n\n"
    prompt += "RTL circuit problem description:\n" + state["problem_description"] + "\n\n"
    prompt += "RTL testbench specification:\n" + state["spec"] + "\n\n"
    prompt += "IMPORTANT - test scenario:\n" + state["scenarios"] + "\n\n"
    prompt += txt2

    llm = get_llm()
    response = llm.invoke(prompt)
    driver_code = extract_code(response.content, "verilog")[-1]
    driver_code = pychecker_CMB_TB_standardization(driver_code, header)
    return {"driver_code": driver_code}


def checklist_node(state: BenchState) -> dict:
    """Verify all planned scenarios appear in driver. Pre-checks with regex before calling LLM."""
    task_id = state["task_id"]

    # ── Pre-check: regex-scan driver for scenarios (no LLM call if all found) ──
    try:
        checklist = json.loads(state["scenarios"])
        missing = []
        for key in checklist.keys():
            # AutoBench format: scenario keys become "scenario_name = value" or "scenario_name" in Verilog
            search_key = key.replace(" ", " = ")
            if search_key not in state["driver_code"] and key not in state["driver_code"]:
                missing.append(key)
        if not missing:
            print(f"[{task_id}] Checklist: all scenarios found (pre-check). Skipping LLM.")
            return {}
    except Exception:
        missing = None  # can't parse JSON → fall through to LLM

    print(f"[{task_id}] Stage checklist: Verifying coverage..." +
          (f" ({len(missing)} missing)" if missing else ""))
    prompt = f"""please check if the testbench code contains all the items in the checklist:
testbench code here...

{state['driver_code']}

please check if the testbench code above contains all the scenarios in the checklist:
{state['scenarios']}
please reply 'YES' if all the items are included. If some of the items are missed in testbench, please add the missing items and reply the modified testbench code (full code)."""
    if missing:
        prompt += f"\nHINT: the missing scenarios may be: {missing}"
    prompt += "\nVERY IMPORTANT: please ONLY reply 'YES' or the full code modified. NEVER remove other irrelevant codes!!!"

    llm = get_llm()
    response = llm.invoke(prompt)
    if "YES" in response.content:
        return {}
    fixed = extract_code(response.content, "verilog")
    return {"driver_code": fixed[-1]} if fixed else {}


def checker_cmb_node(state: BenchState) -> dict:
    """Stage 5 CMB: Generate Python checker."""
    task_id = state["task_id"]
    print(f"[{task_id}] Stage 5 (CMB): Generating checker...")
    header = state["dut_header"]

    signal_template = header_to_SignalTxt_template(header, signal_value="1")
    signal_template_str = str(SignalTxt_to_dictlist(signal_template))

    txt1 = STAGEPYGEN_TXT1 % (signal_template_str, STAGEPYGEN_PYFORMAT)
    txt2 = STAGEPYGEN_TXT2 % STAGEPYGEN_PYFORMAT

    prompt = txt1 + "\n"
    prompt += "RTL circuit problem description:\n" + state["problem_description"] + "\n\n"
    prompt += "Checker specification:\n" + state["spec"] + "\n\n"
    prompt += "Here is the basic rules in python for the module. It is generated in previous stage. You can use it as a reference, but you should write your own python script. This is just for your better understanding:\n"
    prompt += state["golden_rules"] + "\n\n"
    prompt += txt2

    llm = get_llm()
    response = llm.invoke(prompt)
    checker_code = extract_code(response.content, "python")[-1] if extract_code(response.content, "python") else response.content
    return {"checker_code": checker_code + STAGEPYGEN_TAIL}


# ── SEQ Path ──

def driver_seq_node(state: BenchState) -> dict:
    """Stage 4 SEQ: Complete Verilog testbench skeleton."""
    task_id = state["task_id"]
    print(f"[{task_id}] Stage 4 (SEQ): Generating sequential driver...")
    header = state["dut_header"]

    tb_obj = given_TB(header)
    fdisplay_template = fdisplay_code_gen(header, ckeck_en=True)
    txt2 = STAGE4_SEQ_TXT2 % (fdisplay_template, fdisplay_template)

    prompt = STAGE4_SEQ_TXT1 + "\n"
    prompt += "DUT header:\n" + header + "\n\n"
    prompt += "RTL circuit problem description:\n" + state["problem_description"] + "\n\n"
    prompt += "IMPORTANT - test scenario:\n" + state["scenarios"] + "\n\n"
    prompt += "below is the given testbench codes:\n" + tb_obj.gen_template() + "\n\n"
    prompt += txt2

    llm = get_llm()
    response = llm.invoke(prompt)
    driver_code = extract_code(response.content, "verilog")[-1]
    return {"driver_code": driver_code}


def stage4b_node(state: BenchState) -> dict:
    """Stage 4b: Insert $fdisplay after every input change in SEQ driver."""
    task_id = state["task_id"]
    print(f"[{task_id}] Stage 4b: Inserting $fdisplay statements...")
    header = state["dut_header"]

    fdisplay_nocheck = fdisplay_code_gen(header, ckeck_en=False)
    txt2 = Stage4b_SEQ_TXT2 % fdisplay_nocheck
    prompt = Stage4b_SEQ_TXT1 + "\n" + state["driver_code"] + "\n" + txt2

    # Use raw SDK for large prompts (ChatOpenAI hangs on 15K+ tokens)
    response, _ = raw_llm_call(
        [{"role": "user", "content": prompt}],
        model="deepseek-coder",
        api_key_path="../config/key_API.json",
        base_url="https://api.deepseek.com"
    )
    driver_code = extract_code(response, "verilog")[-1]
    driver_code = pychecker_SEQ_TB_standardization(driver_code, header)
    return {"driver_code": driver_code}


def checker_seq_node(state: BenchState) -> dict:
    """Stage 5 SEQ: Generate GoldenDUT class for sequential checker."""
    task_id = state["task_id"]
    print(f"[{task_id}] Stage 5 (SEQ): Generating sequential checker...")
    header = state["dut_header"]

    signal_template = signal_dictlist_template(header, exclude_clk=True)
    txt1 = STAGE5_SEQ_TXT1 % signal_template

    prompt = txt1 + "\n"
    prompt += "DUT circuit problem description:\n" + state["problem_description"] + "\n\n"
    prompt += "The header of DUT (note the input and output signals):\n" + header + "\n\n"
    prompt += "Here is the basic rules in python for the module. It was generated in previous stage. You can use it as a reference, but you should write your own python script. This is just for your better understanding. You can use them or not in your python class\n"
    prompt += state["golden_rules"] + "\n\n"
    prompt += STAGE5_SEQ_TXT2

    llm = get_llm()
    response = llm.invoke(prompt)
    checker_code = extract_code(response.content, "python")[-1] if extract_code(response.content, "python") else response.content
    return {"checker_code": checker_code + STAGE5_SEQ_CODE1 + STAGE5_SEQ_CODE2}


# ── Shared   End Nodes ──

def simulation_node(state: BenchState) -> dict:
    """Run Icarus Verilog + Python checker."""
    task_id = state["task_id"]
    print(f"[{task_id}] Simulation: Running iverilog...")

    work_dir = f"../runs/{task_id}/"
    os.makedirs(work_dir, exist_ok=True)

    with open(os.path.join(work_dir, f"{task_id}.v"), "w") as f:
        f.write(state["dut_code"])
    with open(os.path.join(work_dir, f"{task_id}_tb.v"), "w") as f:
        code = state["driver_code"].replace("```verilog", "").replace("```", "").strip()
        f.write(code)

    iv_result = iverilog_call_and_save(work_dir, silent=True, timeout=60)
    sim_passed = iv_result[0]

    sim_error = ""
    if sim_passed and state.get("checker_code"):
        py_path = os.path.join(work_dir, f"{task_id}_tb.py")
        with open(py_path, "w") as f:
            f.write(state["checker_code"])
        py_result = python_call_and_save(py_path, silent=True, timeout=60)
        sim_passed = py_result[0]
        if not sim_passed:
            # Capture both stderr (traceback) and stdout (checker output)
            py_stderr = py_result[-1] if py_result[-1] else ""
            py_stdout = py_result[1].out if py_result[1] else ""
            sim_error = f"Python checker failed.\nStdout: {py_stdout[:500]}\nStderr: {py_stderr[:500]}"
    elif not sim_passed:
        sim_error = iv_result[-1] if iv_result[-1] else ""

    return {
        "sim_passed": sim_passed,
        "sim_output": iv_result[4].out if iv_result[4] else "",
        "sim_error": sim_error,
    }


def debug_node(state: BenchState) -> dict:
    """Fix broken Verilog OR Python checker using LLM."""
    task_id = state["task_id"]
    iter_count = state.get("debug_iter", 0) + 1
    sim_error = state.get("sim_error", "")
    sim_passed = state.get("sim_passed", False)

    # Decide what to fix: iverilog fails → fix Verilog; checker fails → fix Python
    is_python_error = sim_passed or "python" in sim_error.lower() or "checker" in sim_error.lower() or "traceback" in sim_error.lower() or "indexerror" in sim_error.lower() or "typeerror" in sim_error.lower() or "attributeerror" in sim_error.lower()

    if is_python_error and state.get("checker_code"):
        print(f"[{task_id}] Debug: LLM fixing Python checker (iter {iter_count})...")
        prompt = f"""please fix the python code below according to the error message below. please directly give me the corrected python codes.
Attention: never remove the irrelevant codes!!!
please only reply the full code modified. NEVER remove other irrelevant codes!!!
The python code I give you is the one with error. To be convienient, each of the line begins with a line number. The line number also appears at the error message. You should use the line number to locate the error with the help of error message.

previous python code with error:
{state['checker_code']}

compiling error message:
{sim_error}"""
        llm = get_llm()
        response = llm.invoke(prompt)
        fixed = extract_code(response.content, "python")[-1] if extract_code(response.content, "python") else response.content
        return {"debug_iter": iter_count, "checker_code": fixed}

    else:
        print(f"[{task_id}] Debug: LLM fixing Verilog (iter {iter_count})...")
        prompt = DEBUG_PROMPT.format(
            driver_code=state["driver_code"],
            sim_error=sim_error
        )
        llm = get_llm()
        response = llm.invoke(prompt)
        fixed = extract_code(response.content, "verilog")[-1]
        return {"debug_iter": iter_count, "driver_code": fixed}


def eval_node(state: BenchState) -> dict:
    """Eval0: compile check. Eval1: run against golden RTL. Eval2: run against mutants."""
    task_id = state["task_id"]
    print(f"[{task_id}] Evaluation: Running Eval0/1/2...")

    # Eval0: did it compile and sim?
    sim_passed = state.get("sim_passed", False)
    if not sim_passed:
        return {"eval0_passed": False, "eval1_passed": False, "eval2_passed": False,
                "eval2_mutant_ratio": "0/0"}

    # Eval1: generate & run checker independently against golden RTL
    eval1 = sim_passed  # sim already validates against golden DUT

    # Eval2: AutoBench-style golden TB comparison
    _load_eval_data()
    mutants = _MUTANT_LOOKUP.get(task_id, [])
    golden_tb = _GOLDEN_TB_LOOKUP.get(task_id, "")

    if not mutants:
        return {"eval0_passed": True, "eval1_passed": eval1, "eval2_passed": eval1,
                "eval2_mutant_ratio": "N/A"}

    work_dir = f"../runs/{task_id}/eval2/"
    os.makedirs(work_dir, exist_ok=True)
    matched = 0
    for idx, mutant_code in enumerate(mutants):
        # ── 1. Run GOLDEN TB against mutant ──
        gold_pass = False
        if golden_tb:
            try:
                gold_dir = os.path.join(work_dir, f"golden_{idx}")
                os.makedirs(gold_dir, exist_ok=True)
                with open(os.path.join(gold_dir, f"{task_id}.v"), "w") as f:
                    f.write(mutant_code)
                with open(os.path.join(gold_dir, f"{task_id}_tb.v"), "w") as f:
                    f.write(golden_tb)
                gold_result = iverilog_call_and_save(gold_dir, silent=True, timeout=30)
                if gold_result[0] and gold_result[4]:
                    vvp_out = gold_result[4].out if hasattr(gold_result[4], 'out') else str(gold_result[4])
                    gold_pass = "Mismatches: 0 in" in vvp_out or "All test cases passed" in vvp_out
            except Exception:
                gold_pass = False

        # ── 2. Run GENERATED TB against mutant ──
        gen_pass = False
        try:
            gen_dir = os.path.join(work_dir, f"gen_{idx}")
            os.makedirs(gen_dir, exist_ok=True)
            with open(os.path.join(gen_dir, f"{task_id}.v"), "w") as f:
                f.write(mutant_code)
            with open(os.path.join(gen_dir, f"{task_id}_tb.v"), "w") as f:
                f.write(state["driver_code"])
            gen_result = iverilog_call_and_save(gen_dir, silent=True, timeout=30)
            if gen_result[0] and state.get("checker_code"):
                with open(os.path.join(gen_dir, f"{task_id}_tb.py"), "w") as f:
                    f.write(state["checker_code"])
                py_result = python_call_and_save(
                    os.path.join(gen_dir, f"{task_id}_tb.py"), silent=True, timeout=30)
                checker_out = py_result[1].out.strip() if py_result[1] else ""
                gen_pass = checker_out == "[]"
            elif gen_result[0]:
                gen_pass = True  # compiled, no checker
        except Exception:
            gen_pass = False

        # ── 3. Verdicts match? ──
        if gold_pass == gen_pass:
            matched += 1  # both pass or both fail = our TB agrees with golden TB

    ratio = f"{matched}/{len(mutants)}"
    eval2 = matched >= len(mutants) * 0.8  # AutoBench's LOOSE_FACTOR = 0.8

    return {
        "eval0_passed": True,
        "eval1_passed": eval1,
        "eval2_passed": eval2,
        "eval2_mutant_ratio": ratio,
    }


def vcd_node(state: BenchState) -> dict:
    task_id = state["task_id"]
    print(f"[{task_id}] VCD Analysis: placeholder...")
    return {"waveform_analysis": "placeholder"}


def reboot_node(state: BenchState) -> dict:
    """Regenerate driver from scratch when debug patching fails."""
    task_id = state["task_id"]
    print(f"[{task_id}] Reboot: Regenerating driver from scratch...")
    if state["circuit_type"] == "CMB":
        result = driver_cmb_node(state)
    else:
        result = driver_seq_node(state)
    result["reboot_count"] = state.get("reboot_count", 0) + 1
    result["debug_iter"] = 0
    return result


# ═══════════════════════════════════════════════════
# Routing
# ═══════════════════════════════════════════════════

def should_retry(state: BenchState) -> str:
    """After simulation: eval (pass), debug (fix), or reboot (regenerate)."""
    if state.get("sim_passed", False):
        return "eval"
    if state.get("reboot_count", 0) >= 2:
        return "eval"           # max 2 reboots, then give up
    total = state.get("debug_iter", 0) + state.get("reboot_count", 0)
    if total >= 5:
        return "eval"           # exhausted, mark as failed
    if state.get("debug_iter", 0) >= 2:
        return "reboot"         # 2 debugs failed → regenerate
    return "debug"


def route_circuit(state: BenchState) -> str:
    return "cmb" if state["circuit_type"] == "CMB" else "seq"


# ═══════════════════════════════════════════════════
# Build Graph
# ═══════════════════════════════════════════════════

def build_graph() -> StateGraph:
    builder = StateGraph(BenchState)

    # Shared stages
    builder.add_node("classify", classify_node)
    builder.add_node("spec", spec_node)
    builder.add_node("scenarios", scenarios_node)
    builder.add_node("rules", rules_node)

    # CMB path
    builder.add_node("driver_cmb", driver_cmb_node)
    builder.add_node("checklist", checklist_node)
    builder.add_node("checker_cmb", checker_cmb_node)

    # SEQ path
    builder.add_node("driver_seq", driver_seq_node)
    builder.add_node("stage4b", stage4b_node)
    builder.add_node("checker_seq", checker_seq_node)

    # Shared end
    builder.add_node("simulation", simulation_node)
    builder.add_node("debug", debug_node)
    builder.add_node("reboot", reboot_node)
    builder.add_node("eval", eval_node)
    builder.add_node("vcd", vcd_node)

    # Linear: START → classify → spec → scenarios → rules
    builder.add_edge(START, "classify")
    builder.add_edge("classify", "spec")
    builder.add_edge("spec", "scenarios")
    builder.add_edge("scenarios", "rules")

    # Branch CMB vs SEQ
    builder.add_conditional_edges("rules", route_circuit, {
        "cmb": "driver_cmb",
        "seq": "driver_seq",
    })

    # CMB path
    builder.add_edge("driver_cmb", "checklist")

    # SEQ path
    builder.add_edge("driver_seq", "checklist")

    # Branch after checklist based on circuit type
    builder.add_conditional_edges("checklist", route_circuit, {
        "cmb": "checker_cmb",
        "seq": "stage4b",
    })
    builder.add_edge("stage4b", "checker_seq")

    # Merge at simulation
    builder.add_edge("checker_cmb", "simulation")
    builder.add_edge("checker_seq", "simulation")

    # Debug loop with reboot
    builder.add_conditional_edges("simulation", should_retry, {
        "eval": "eval",
        "debug": "debug",
        "reboot": "reboot",
    })
    builder.add_edge("debug", "simulation")
    builder.add_edge("reboot", "simulation")

    # Eval → VCD → END
    builder.add_edge("eval", "vcd")
    builder.add_edge("vcd", END)

    return builder.compile()


# ═══════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    graph = build_graph()
    # Skip already-tested + problems that hang DeepSeek on large prompts
    # Load already-completed problems
    results_path = "../results/graph_results.json"
    skip_set = set()
    if os.path.exists(results_path):
        with open(results_path) as f:
            for r in json.load(f):
                skip_set.add(r["task_id"])
    # Large SEQ circuits — stage4b prompt too big, DeepSeek hangs
    skip_set.update({"lemmings4", "gshare", "review2015_fancytimer", "lemmings3",
                     "circuit10", "review2015_fsm", "2013_q2bfsm"})
    with open("../data/HDLBits/HDLBits_data.jsonl") as f:
        problems = [json.loads(line) for line in f.readlines()][:10]
        problems = [p for p in problems if p["task_id"] not in skip_set]

    results = []
    for i, prob in enumerate(problems):
        print(f"\n{'='*60}")
        print(f"PROBLEM {i+1}/{len(problems)}: {prob['task_id']}")
        print(f"{'='*60}")

        result = graph.invoke({
            "task_id": prob["task_id"],
            "task_number": prob["task_number"],
            "problem_description": prob["description"],
            "dut_header": prob["header"],
            "dut_code": prob["module_code"],
            "circuit_type": "",
            "spec": "",
            "scenarios": "",
            "golden_rules": "",
            "driver_code": "",
            "checker_code": "",
            "sim_passed": False,
            "sim_output": "",
            "sim_error": "",
            "debug_iter": 0,
            "reboot_count": 0,
            "eval0_passed": False,
            "eval1_passed": False,
            "eval2_passed": False,
            "eval2_mutant_ratio": "",
            "vcd_path": "",
            "waveform_analysis": "",
            "errors": [],
        })

        results.append({
            "task_id": prob["task_id"],
            "circuit_type": result["circuit_type"],
            "sim_passed": result["sim_passed"],
            "eval0": result["eval0_passed"],
            "eval1": result.get("eval1_passed"),
            "eval2": result.get("eval2_passed"),
            "eval2_ratio": result.get("eval2_mutant_ratio"),
        })
        print(f"{prob['task_id']}: {result['circuit_type']}, "
              f"pass={result['sim_passed']}, E2={result.get('eval2_mutant_ratio','?')}, "
              f"debug={result['debug_iter']}")

        # Save incrementally every 10 problems
        if (i + 1) % 10 == 0:
            save_path = "../results/graph_results.json"
            os.makedirs("../results", exist_ok=True)
            with open(save_path, "w") as f:
                json.dump(results, f, indent=2)
            print(f"  [Saved {len(results)} results]")

    # Summary
    passed = sum(1 for r in results if r["sim_passed"])
    eval0 = sum(1 for r in results if r.get("eval0"))
    eval1 = sum(1 for r in results if r.get("eval1"))
    eval2 = sum(1 for r in results if r.get("eval2"))
    cmb = sum(1 for r in results if r["circuit_type"] == "CMB")
    seq = sum(1 for r in results if r["circuit_type"] == "SEQ")
    print(f"\n{'='*60}")
    if len(results) != 0:
        print(f"SUMMARY: {passed}/{len(results)} sim passed ({passed/len(results)*100:.1f}%)")
    print(f"Eval0: {eval0}, Eval1: {eval1}, Eval2: {eval2}")
    print(f"CMB: {cmb}, SEQ: {seq}")

    # Final save
    save_path = "../results/graph_results.json"
    os.makedirs("../results", exist_ok=True)
    with open(save_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[Results saved to {save_path}]")
