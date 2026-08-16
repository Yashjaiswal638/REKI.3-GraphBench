"""StateGraph definition for GraphBench pipeline."""
import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))  # src/
from reki3.plumbing.iverilog_call import iverilog_call_and_save
from reki3.plumbing.python_call import python_call_and_save
from langgraph.graph import StateGraph, START, END
from reki3.plumbing.llm_call import extract_code, llm_call as raw_llm_call
from reki3.core.verilog_utils import (
    given_TB,
    fdisplay_code_gen,
    pychecker_CMB_TB_standardization,
    pychecker_SEQ_TB_standardization,
    header_to_SignalTxt_template,
    SignalTxt_to_dictlist,
    signal_dictlist_template,
    circuit_type_by_code,
)
from reki3.core.prompts import *
from langchain_openai import ChatOpenAI
import json as json_module

# Project root, resolved from this file — immune to the working directory.
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "..")

VCD_ENABLED = True   # True = use .vcd waveform files, False = use TBout.txt

SIGNALTEMP_PLACEHOLDER_1 = "/* SIGNAL TEMPLATE 1 */"
SIGNALTEMP_PLACEHOLDER_1A = "/* SIGNAL TEMPLATE 1A */"
SIGNALTEMP_PLACEHOLDER_1B = "/* SIGNAL TEMPLATE 1B */"

# VCD dumpfile instruction (appended to driver prompts when VCD_ENABLED)
VCD_INSTRUCTION = """
CRITICAL: You MUST add these lines at the start of the initial block:
$dumpfile("dump.vcd");
$dumpvars(0, testbench);
This generates a waveform file for debugging."""
VCD_INSTRUCTION_SEQ = """
CRITICAL: You MUST add these lines at the start of the initial block (before the scenario code):
$dumpfile("dump.vcd");
$dumpvars(0, testbench);
This generates a waveform file for debugging."""

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
    mutant_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "..", "data", "HDLBits", "HDLBits_data_mutants.jsonl")
    if os.path.exists(mutant_path):
        with open(mutant_path) as f:
            for line in f:
                m = json.loads(line)
                _MUTANT_LOOKUP[m["task_id"]] = m.get("mutants", [])
    # Load golden TBs from main dataset
    data_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "..", "data", "HDLBits", "HDLBits_data.jsonl")
    if os.path.exists(data_path):
        with open(data_path) as f:
            for line in f:
                d = json.loads(line)
                _GOLDEN_TB_LOOKUP[d["task_id"]] = d.get("testbench", "")

def get_llm():
    key_path = os.path.join(ROOT, "config", "key_API.json")
    with open(key_path) as f:
        api_key = json_module.load(f)["OPENAI_API_KEY"]
    return ChatOpenAI(
        model="deepseek-coder",
        api_key=api_key,
        base_url="https://api.deepseek.com",
        temperature=0,
        request_timeout=300  # 5 min per LLM call
    )


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Node Functions
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def classify_node(state: dict) -> dict:
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

def spec_node(state: dict) -> dict:
    task_id = state["task_id"]
    print(f"[{task_id}] Stage 1: Generating spec...")

    prompt = SPEC_PROMPT.format(
        problem_description=state["problem_description"],
        dut_header=state["dut_header"]
    )

    llm = get_llm()
    response = llm.invoke(prompt)

    return {"spec": response.content}


def scenarios_node(state: dict) -> dict:
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


def rules_node(state: dict) -> dict:
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


# â”€â”€ CMB Path â”€â”€

def driver_cmb_node(state: dict) -> dict:
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
    if VCD_ENABLED:
        prompt += VCD_INSTRUCTION

    llm = get_llm()
    response = llm.invoke(prompt)
    driver_code = extract_code(response.content, "verilog")[-1]
    driver_code = pychecker_CMB_TB_standardization(driver_code, header)
    return {"driver_code": driver_code}


def checklist_node(state: dict) -> dict:
    """Verify all planned scenarios appear in driver. Regex pre-check, LLM if needed."""
    task_id = state["task_id"]

    # Pre-check: regex-scan driver for scenarios (skip LLM if all found)
    try:
        checklist = json.loads(state["scenarios"])
        missing = []
        for key in checklist.keys():
            search_key = key.replace(" ", " = ")
            if search_key not in state["driver_code"] and key not in state["driver_code"]:
                missing.append(key)
        if not missing:
            print(f"[{task_id}] Checklist: all scenarios found (pre-check). Skipping LLM.")
            return {}
    except Exception:
        missing = None

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


def checker_cmb_node(state: dict) -> dict:
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


# â”€â”€ SEQ Path â”€â”€

def driver_seq_node(state: dict) -> dict:
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
    if VCD_ENABLED:
        prompt += VCD_INSTRUCTION_SEQ

    llm = get_llm()
    response = llm.invoke(prompt)
    driver_code = extract_code(response.content, "verilog")[-1]
    return {"driver_code": driver_code}


def stage4b_node(state: dict) -> dict:
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
        api_key_path=os.path.join(ROOT, "config", "key_API.json"),
        base_url="https://api.deepseek.com"
    )
    driver_code = extract_code(response, "verilog")[-1]
    driver_code = pychecker_SEQ_TB_standardization(driver_code, header)
    return {"driver_code": driver_code}


def checker_seq_node(state: dict) -> dict:
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


# â”€â”€ Shared   End Nodes â”€â”€

def simulation_node(state: dict) -> dict:
    """Run Icarus Verilog + Python checker."""
    task_id = state["task_id"]
    print(f"[{task_id}] Simulation: Running iverilog...")

    work_dir = os.path.join(ROOT, "runs", task_id) + os.sep
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


def debug_node(state: dict) -> dict:
    """Fix broken Verilog OR Python checker using LLM."""
    task_id = state["task_id"]
    iter_count = state.get("debug_iter", 0) + 1
    sim_error = state.get("sim_error", "")
    sim_passed = state.get("sim_passed", False)

    # Include diagnosis if available (from vcd_node)
    diagnosis = state.get("waveform_analysis", "")
    diagnosis_hint = f"\n\nDiagnosis of the failure (use this to target your fix):\n{diagnosis}" if diagnosis and diagnosis != "placeholder" else ""

    # Decide what to fix: iverilog fails â†’ fix Verilog; checker fails â†’ fix Python
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
{sim_error}{diagnosis_hint}"""
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
        prompt += diagnosis_hint
        llm = get_llm()
        response = llm.invoke(prompt)
        fixed = extract_code(response.content, "verilog")[-1]
        return {"debug_iter": iter_count, "driver_code": fixed}


def eval_node(state: dict) -> dict:
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

    work_dir = os.path.join(ROOT, "runs", task_id, "eval2") + os.sep
    os.makedirs(work_dir, exist_ok=True)
    matched = 0
    evaluated = 0
    for idx, mutant_code in enumerate(mutants):
        # 1. Run GOLDEN TB against mutant
        gold_pass = False
        gold_valid = False
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
                    gold_valid = True
                    vvp_out = gold_result[4].out if hasattr(gold_result[4], 'out') else str(gold_result[4])
                    gold_pass = "Mismatches: 0 in" in vvp_out or "All test cases passed" in vvp_out
            except Exception:
                gold_valid = False

        if not gold_valid:
            continue

        # â”€â”€ 2. Run GENERATED TB against mutant â”€â”€
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

        # 3. Verdicts match?
        if gold_pass == gen_pass:
            matched += 1
        evaluated += 1

    if evaluated == 0:
        return {"eval0_passed": True, "eval1_passed": eval1, "eval2_passed": False,
                "eval2_mutant_ratio": "0/0 (no valid golden verdicts)"}
    ratio = f"{matched}/{evaluated}"
    eval2 = matched >= evaluated * 0.8

    return {
        "eval0_passed": True,
        "eval1_passed": eval1,
        "eval2_passed": eval2,
        "eval2_mutant_ratio": ratio,
    }


def vcd_node(state: dict) -> dict:
    """Analyze simulation signal data to diagnose WHY a testbench failed."""
    task_id = state["task_id"]
    if state.get("sim_passed"):
        return {"waveform_analysis": "PASSED â€” no diagnosis needed."}

    print(f"[{task_id}] VCD Analysis: Diagnosing failure...")

    # Read signal data: VCD file (if enabled) or TBout.txt (fallback)
    signal_table = "(no signal data)"
    if VCD_ENABLED:
        vcd_path = f"../runs/{task_id}/dump.vcd"
        if os.path.exists(vcd_path):
            try:
                from vcdvcd import VCDVCD
                vcd = VCDVCD(vcd_path)
                lines = []
                for sig_name in vcd.signals:
                    sig_data = vcd[sig_name]
                    changes = sig_data.tv if hasattr(sig_data, 'tv') else []
                    if changes:
                        values = ", ".join(f"{t}={v}" for t, v in changes[:10])
                        lines.append(f"{sig_name}: {values}")
                signal_table = "\n".join(lines) if lines else "(empty VCD)"
            except Exception:
                pass  # fall through to TBout.txt
    if signal_table == "(no signal data)":
        tbout_path = f"../runs/{task_id}/TBout.txt"
        if os.path.exists(tbout_path):
            with open(tbout_path) as f:
                signal_lines = f.read().strip().splitlines()[:40]
            signal_table = "\n".join(signal_lines) if signal_lines else "(no signal data)"

    # Build context: what should the circuit do?
    spec = state.get("spec", "")[:300]
    rules = state.get("golden_rules", "")[:500]
    description = state.get("problem_description", "")[:200]

    prompt = f"""Diagnose a hardware testbench failure.

## Circuit Description
{description}

## Expected Behavior (Golden Rules)
```python
{rules}
```

## Actual Signal Output (TBout.txt)
{signal_table}

## Error
{state.get('sim_error', 'No error captured')[:400]}

## Instructions
1. If the error is a COMPILATION ERROR (syntax, undefined macro): state the exact error and suggest a Verilog fix.
2. If signals are present: compare each signal against the expected behavior from the golden rules above.
3. Identify WHICH signal is wrong, at WHICH scenario, and what the CORRECT value should be.
4. Determine root cause: timing issue? wrong expected value? missing test case?
5. Suggest ONE specific fix for the testbench code.

Reply in 2-4 sentences. Be specific â€” mention signal names and scenario numbers."""

    llm = get_llm()
    response = llm.invoke(prompt)
    diagnosis = response.content.strip()
    print(f"[{task_id}] Diagnosis: {diagnosis[:200]}...")
    return {"waveform_analysis": diagnosis}


def reboot_node(state: dict) -> dict:
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


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â••â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•ââ•â•â•â•â•â•â•â•â•â•â•â•
