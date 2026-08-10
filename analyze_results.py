"""Merge and analyze all benchmark results for AutoBench comparison."""
import json, os

def load_results(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)

# Load both result sets
graph_results = load_results("results/graph_results.json")
agent_results = load_results("results/agent_results.json")

# Merge: start with graph, agent fills gaps but doesn't overwrite good data
merged = {}
for r in graph_results:
    merged[r["task_id"]] = dict(r)
for r in agent_results:
    tid = r["task_id"]
    if tid not in merged:
        merged[tid] = dict(r)
    else:
        # Only update fields that are missing/None in graph result
        for k, v in r.items():
            if merged[tid].get(k) in (None, False, "", 0) and v not in (None, False, "", 0):
                merged[tid][k] = v

results = list(merged.values())
results.sort(key=lambda r: r["task_id"])

# Compute metrics
total = len(results)
sim_passed = sum(1 for r in results if r.get("sim_passed"))
eval0 = sum(1 for r in results if r.get("eval0_passed"))
eval1 = sum(1 for r in results if r.get("eval1_passed"))
eval2 = sum(1 for r in results if r.get("eval2_passed"))
cmb = sum(1 for r in results if r.get("circuit_type") == "CMB")
seq = sum(1 for r in results if r.get("circuit_type") == "SEQ")

# Eval2 ratios
ratios = []
for r in results:
    ratio_str = r.get("eval2_mutant_ratio", "0/0")
    if "/" in ratio_str:
        parts = ratio_str.split("/")
        try:
            num, den = int(parts[0]), int(parts[1])
            if den > 0:
                ratios.append(num / den)
        except ValueError:
            pass

avg_eval2_ratio = sum(ratios) / len(ratios) * 100 if ratios else 0

print(f"{'='*60}")
print(f"REKI.3 GraphBench — Final Results")
print(f"{'='*60}")
print(f"Total problems: {total}")
print(f"  CMB: {cmb}, SEQ: {seq}")
print(f"")
print(f"Eval0 (compiles):     {eval0}/{total} = {eval0/total*100:.1f}%")
print(f"Eval1 (golden pass):  {eval1}/{total} = {eval1/total*100:.1f}%")
print(f"Eval2 (mutant det):   {eval2}/{total} = {eval2/total*100:.1f}%")
print(f"Full pass (sim):      {sim_passed}/{total} = {sim_passed/total*100:.1f}%")
print(f"")
print(f"Average Eval2 mutant coverage: {avg_eval2_ratio:.1f}%")
print(f"")
print(f"AutoBench paper (GPT-4):    52.18% full pass")
print(f"CorrectBench paper (GPT-4): 70.13% full pass")
print(f"REKI.3 (DeepSeek Coder):    {sim_passed/total*100:.2f}% full pass (sim)")
print(f"REKI.3 (DeepSeek Coder):    {eval2/total*100:.2f}% full pass (Eval2)")

# Failed problems
print(f"\n--- Failed Problems ---")
for r in results:
    if not r.get("sim_passed"):
        print(f"  {r['task_id']}: sim failed")
for r in results:
    if r.get("sim_passed") and not r.get("eval2_passed"):
        ratio = r.get('eval2_mutant_ratio') or 'N/A'
        print(f"  {r['task_id']}: Eval2={ratio}")

# Save merged
os.makedirs("results", exist_ok=True)
with open("results/merged_results.json", "w") as f:
    json.dump(results, f, indent=2)

print(f"\n[Merged results saved to results/merged_results.json]")
print(f"[Graph: {len(graph_results)}, Agent: {len(agent_results)}, Merged: {total}]")
