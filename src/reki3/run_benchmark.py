"""Benchmark runner for the LangGraph agent implementation.

Run from src/ (WSL):
    source ~/reki3-venv/bin/activate
    cd /mnt/d/Projects/REKI.3-GraphBench/src
    python -m langgraph_agent.run_benchmark

Writes results to ../results/langgraph_agent_results.json — separate from the
Python-loop agent's agent_results.json so both implementations can be compared
(ablation for the thesis). Resumes from that file on restart.
"""
import os, sys, json, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # src/
ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..")

from reki3.agent.graph import agent_loop

def init_state(prob):
    return {
        "task_id": prob["task_id"], "task_number": prob["task_number"],
        "problem_description": prob["description"], "dut_header": prob["header"],
        "dut_code": prob["module_code"], "circuit_type": "", "spec": "",
        "scenarios": "", "golden_rules": "", "driver_code": "", "checker_code": "",
        "sim_passed": False, "sim_output": "", "sim_error": "",
        "debug_iter": 0, "reboot_count": 0,
        "eval0_passed": False, "eval1_passed": False, "eval2_passed": False,
        "eval2_mutant_ratio": "", "eval2b_passed": False, "eval2b_ratio": "",
        "vcd_path": "", "waveform_analysis": "",
        "errors": [],
    }

if __name__ == "__main__":
    hang = {"lemmings4", "gshare", "review2015_fancytimer", "lemmings3",
            "circuit10", "review2015_fsm", "2013_q2bfsm", "fsm_ps2data",
            "ece241_2013_q8"}
    # The 9 former hang-set problems now run (timeout guards make them feasible);
    # only mux9to1v is skipped (persistent hang/crash) → 155 of 156.
    skip = {"mux9to1v"}
    # TEMP: first 10 problems — smoke test after cleanup
    PROBLEM_SLICE = slice(0, 10)

    results = []
    results_path = os.path.join(ROOT, "results", "langgraph_agent_results.json")
    if os.path.exists(results_path):
        with open(results_path) as f:
            results = json.load(f)
    done = {r["task_id"] for r in results}
    if done:
        print(f"Resuming: {len(done)} problems already in {results_path} — skipping them.")

    with open(os.path.join(ROOT, "data", "HDLBits", "HDLBits_data.jsonl")) as f:
        problems = [json.loads(line) for line in f.readlines()]
        problems = [p for p in problems[PROBLEM_SLICE]
                    if p["task_id"] not in skip and p["task_id"] not in done]

    if not problems:
        print("No problems left to run — benchmark already complete.")
        exit(0)

    for i, prob in enumerate(problems):
        print(f"\n{'='*60}")
        print(f"PROBLEM {i+1}/{len(problems)}: {prob['task_id']}")
        print(f"{'='*60}")

        state = init_state(prob)
        try:
            result = agent_loop(state)
            results.append(result)
            print(f"{result['task_id']}: {result['circuit_type']}, "
                  f"pass={result['sim_passed']}, "
                  f"E2={result.get('eval2_mutant_ratio','?')}, "
                  f"d={result.get('debug_iter',0)} r={result.get('reboot_count',0)}")
        except Exception as e:
            print(f"ERROR: {e}")
            traceback.print_exc()

        # Save after every problem (crash-safe: a restart skips completed work)
        os.makedirs("../results", exist_ok=True)
        with open(results_path, "w") as f:
            json.dump([{k: r.get(k) for k in ["task_id","circuit_type","sim_passed",
                "eval0_passed","eval1_passed","eval2_passed","eval2_mutant_ratio",
                "eval2b_passed","eval2b_ratio",
                "debug_iter","reboot_count"]} for r in results], f, indent=2)
        print(f"  [Saved {len(results)}]")

    # Summary
    passed = sum(1 for r in results if r.get("sim_passed"))
    eval2 = sum(1 for r in results if r.get("eval2_passed"))
    full_pass = sum(1 for r in results
                    if r.get("sim_passed") and r.get("eval0_passed")
                    and r.get("eval1_passed") and r.get("eval2_passed"))
    cmb = sum(1 for r in results if r.get("circuit_type") == "CMB")
    seq = sum(1 for r in results if r.get("circuit_type") == "SEQ")
    print(f"\n{'='*60}")
    print(f"LANGGRAPH AGENT SUMMARY: {passed}/{len(results)} sim passed ({passed/len(results)*100:.1f}%)" if results else "SUMMARY: 0")
    print(f"Eval2: {eval2}/{len(results)}, CMB: {cmb}, SEQ: {seq}")
    print(f"Full pass (AutoBench headline, sim+Eval1+Eval2): "
          f"{full_pass}/{len(results)} ({full_pass/len(results)*100:.1f}%)")

    os.makedirs("../results", exist_ok=True)
    with open(results_path, "w") as f:
        json.dump([{k: r.get(k) for k in ["task_id","circuit_type","sim_passed",
            "eval0_passed","eval1_passed","eval2_passed","eval2_mutant_ratio",
            "eval2b_passed","eval2b_ratio",
            "debug_iter","reboot_count"]} for r in results], f, indent=2)
    print(f"[Saved to {results_path}]")
