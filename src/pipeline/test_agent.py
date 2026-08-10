"""Test the LLM agent on 10 circuit problems."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pipeline.agent import agent_loop

def init_state(prob):
    return {
        "task_id": prob["task_id"], "task_number": prob["task_number"],
        "problem_description": prob["description"], "dut_header": prob["header"],
        "dut_code": prob["module_code"], "circuit_type": "", "spec": "",
        "scenarios": "", "golden_rules": "", "driver_code": "", "checker_code": "",
        "sim_passed": False, "sim_output": "", "sim_error": "",
        "debug_iter": 0, "reboot_count": 0,
        "eval0_passed": False, "eval1_passed": False, "eval2_passed": False,
        "eval2_mutant_ratio": "", "vcd_path": "", "waveform_analysis": "",
        "errors": [],
    }

if __name__ == "__main__":
    # Skip already-completed problems
    skip_set = set()
    results_path = "../results/graph_results.json"
    if os.path.exists(results_path):
        with open(results_path) as f:
            for r in json.load(f):
                skip_set.add(r["task_id"])

    # Skip already-done + problems that hang DeepSeek (too large)
    hang_set = {"lemmings4", "gshare", "review2015_fancytimer", "lemmings3",
                "circuit10", "review2015_fsm", "2013_q2bfsm", "fsm_ps2data"}
    skip_set.update(hang_set)

    with open("../data/HDLBits/HDLBits_data.jsonl") as f:
        problems = [json.loads(line) for line in f.readlines()]
        problems = [p for p in problems if p["task_id"] not in skip_set]  # all

    results = []
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

        # Save every 10
        if (i + 1) % 10 == 0:
            os.makedirs("../results", exist_ok=True)
            with open("../results/agent_results.json", "w") as f:
                json.dump([{k: r.get(k) for k in ["task_id","circuit_type","sim_passed",
                    "eval0_passed","eval1_passed","eval2_passed","eval2_mutant_ratio",
                    "debug_iter","reboot_count"]} for r in results], f, indent=2)
            print(f"  [Saved {len(results)}]")

    # Summary
    passed = sum(1 for r in results if r.get("sim_passed"))
    eval2 = sum(1 for r in results if r.get("eval2_passed"))
    cmb = sum(1 for r in results if r.get("circuit_type") == "CMB")
    seq = sum(1 for r in results if r.get("circuit_type") == "SEQ")
    print(f"\n{'='*60}")
    print(f"SUMMARY: {passed}/{len(results)} sim passed ({passed/len(results)*100:.1f}%)" if results else "SUMMARY: 0")
    print(f"Eval2: {eval2}/{len(results)}, CMB: {cmb}, SEQ: {seq}")

    # Save
    save_path = "../results/agent_results.json"
    os.makedirs("../results", exist_ok=True)
    with open(save_path, "w") as f:
        json.dump([{k: r[k] for k in ["task_id","circuit_type","sim_passed",
            "eval0_passed","eval1_passed","eval2_passed","eval2_mutant_ratio",
            "debug_iter","reboot_count"]} for r in results], f, indent=2)
    print(f"[Saved to {save_path}]")
