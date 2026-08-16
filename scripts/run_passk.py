"""pass@k sampling for the REKI.3 LangGraph agent.

Runs a chosen subset of problems N times each, saves per-run results, and
computes the unbiased pass@k estimator (Codex formula):

    pass@k = 1 - C(n-c, k) / C(n, k)      (n samples, c successes)

Usage (from repo root, WSL):
    source ~/reki3-venv/bin/activate
    python scripts/run_passk.py                # batch slice, n=3
    REKI3_SKIP_EVAL2B=1 python scripts/run_passk.py   # skip Eval2b (faster)

Only pass@1..pass@3 are reported (cost decision).

Resumable: completed (task, run) pairs are skipped on restart.
Results: results/passk_samples.json
"""
import os, sys, json, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reki3.agent.graph import agent_loop

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(ROOT, "data", "HDLBits", "HDLBits_data.jsonl")
OUT = os.path.join(ROOT, "results", "passk_samples.json")

N_RUNS = int(os.environ.get("N_RUNS", "3"))   # 3: cost decision — report only up to pass@3

# Batch slice over the dataset — currently the second batch (indices 20-39).
SUBSET_SLICE = slice(40, 60)

METRICS = ["sim_passed", "eval0_passed", "eval1_passed", "eval2_passed"]


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


def pass_at_k(n, c, k):
    if n - c < k:
        return 1.0
    if c == 0:
        return 0.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def main():
    with open(DATA) as f:
        probs = [json.loads(l) for l in f.readlines()]
    probs = probs[SUBSET_SLICE]
    SUBSET = [p["task_id"] for p in probs]

    samples = {}
    if os.path.exists(OUT):
        with open(OUT) as f:
            samples = json.load(f)
    samples.setdefault("samples", {})

    total = len(probs) * N_RUNS
    done_count = 0
    for prob in probs:
        tid = prob["task_id"]
        samples["samples"].setdefault(tid, [])
        for run in range(N_RUNS):
            if run < len(samples["samples"][tid]):
                done_count += 1
                continue
            print(f"\n{'='*60}\n{tid} — run {run+1}/{N_RUNS}\n{'='*60}")
            try:
                out = agent_loop(init_state(prob))
                samples["samples"][tid].append({
                    "run": run, "sim_passed": out.get("sim_passed"),
                    "eval0_passed": out.get("eval0_passed"),
                    "eval1_passed": out.get("eval1_passed"),
                    "eval2_passed": out.get("eval2_passed"),
                    "eval2_mutant_ratio": out.get("eval2_mutant_ratio"),
                    "debug_iter": out.get("debug_iter"), "reboot_count": out.get("reboot_count"),
                })
            except Exception as e:
                print(f"ERROR: {e}")
                samples["samples"][tid].append({"run": run, "error": str(e)})
            os.makedirs(os.path.dirname(OUT), exist_ok=True)
            with open(OUT, "w") as f:
                json.dump(samples, f, indent=2)
            done_count += 1
            last = samples["samples"][tid][-1]
            if "error" in last:
                print(f"{tid} run {run+1}: ERROR")
            else:
                full = bool(last.get("sim_passed") and last.get("eval1_passed")
                            and last.get("eval2_passed"))
                print(f"{tid} run {run+1}: sim={last.get('sim_passed')}, "
                      f"E2={last.get('eval2_mutant_ratio')}, full={full}, "
                      f"d={last.get('debug_iter')} r={last.get('reboot_count')}")
            print(f"[{done_count}/{total} saved]")

    # ---- pass@k computation ----
    print(f"\n{'='*60}\npass@k results (n={N_RUNS} per problem, {len(probs)} problems)\n{'='*60}")
    n = N_RUNS
    for metric in METRICS:
        counts = []
        for tid in SUBSET:
            runs = samples["samples"].get(tid, [])
            c = sum(1 for r in runs if r.get(metric))
            counts.append(c)
        line = f"{metric:16s} pass@1={sum(1 for c in counts if c>=1)/len(counts)*100:5.1f}%"
        for k in range(2, min(n, 3) + 1):
            line += f"  pass@{k}={sum(pass_at_k(n, c, k) for c in counts)/len(counts)*100:5.1f}%"
        print(line)
    full = []
    for tid in SUBSET:
        runs = samples["samples"].get(tid, [])
        full.append(sum(1 for r in runs if r.get("sim_passed") and r.get("eval1_passed") and r.get("eval2_passed")))
    line = f"{'FULL PASS':16s} pass@1={sum(1 for c in full if c>=1)/len(full)*100:5.1f}%"
    for k in range(2, min(n, 3) + 1):
        line += f"  pass@{k}={sum(pass_at_k(n, c, k) for c in full)/len(full)*100:5.1f}%"
    print(line)
    print(f"\n[samples saved to {OUT}]")


if __name__ == "__main__":
    main()
