"""LLM Agent — LLM autonomously selects tools. Code only enforces hard safety limits."""
from pipeline.tools import TOOLS
from pipeline.graph import get_llm

PROMPT = """Tools: {tools}

Progress: {progress}

Errors: {errors}

Pick ONE tool. Reply with only the tool name."""  # No "DONE" — eval means done


def agent_loop(initial_state, max_steps=30):
    state = dict(initial_state)
    llm = get_llm()
    history = []

    for step in range(max_steps):
        # ── Hard safety limits (code-enforced, LLM cannot override) ──
        if state.get("eval2_mutant_ratio", ""):
            break
        d = state.get("debug_iter", 0)
        r = state.get("reboot_count", 0)
        # Track TOTAL retries across reboots (don't let reboot reset allow infinite loops)
        total_retries = state.get("_total_retries", 0)
        if d + r > total_retries:
            state["_total_retries"] = d + r
            total_retries = d + r
        if d >= 4 or r >= 2 or total_retries >= 6:
            if not state.get("eval2_mutant_ratio"):
                print(f"[A] Safety: forcing eval (d={d} r={r} total={total_retries})")
                TOOLS["eval"]["fn"](state)
            break

        # ── Build tool list with descriptions ──
        tools_str = "\n".join(f"  {n}: {t['desc']}" for n, t in TOOLS.items())

        # ── Build progress summary (DONE first, then what's MISSING) ──
        ct = state.get("circuit_type", "?")
        done = []
        missing = []
        if ct and ct != "?":
            done.append(f"classified as {ct}")
        else:
            missing.append("classify (unknown circuit type)")
        if state.get("spec"):
            done.append("spec ready")
        else:
            missing.append("spec (no specification)")
        if state.get("scenarios"):
            done.append("scenarios ready")
        else:
            missing.append("scenarios (no test plan)")
        if state.get("golden_rules"):
            done.append("rules ready")
        else:
            missing.append("rules (no golden reference)")
        if state.get("driver_code"):
            done.append("driver ready")
        else:
            missing.append("driver (no Verilog testbench)")
        if state.get("checker_code"):
            done.append("checker ready")
        else:
            # Auto-insert checklist if driver exists but checklist wasn't called
            if state.get("driver_code") and not state.get("checker_code"):
                if "checklist" not in [h for h in history[-5:] if h]:
                    missing.append("checklist (verify driver coverage first!)")
            missing.append("checker (no Python validator)")
        if state.get("driver_code") and state.get("checker_code") and not state.get("sim_passed") and d == 0 and r == 0:
            done.append("READY TO SIMULATE")
        if state.get("sim_passed"):
            done.append("simulation PASSED")
        elif d > 0 or r > 0:
            done.append(f"simulation FAILED (debug={d}, reboot={r})")

        progress = "DONE: " + (", ".join(done) if done else "nothing yet")
        if missing:
            progress += "\nMISSING: " + ", ".join(missing)
        if ct and ct != "?":
            progress += f"\nCircuit type: {ct} — use {'driver_cmb/checker_cmb' if ct == 'CMB' else 'driver_seq/stage4b/checker_seq'}"

        # ── Build error context ──
        errors = ""
        sim_err = state.get("sim_error", "")
        if sim_err and not state.get("sim_passed"):
            errors = f"Last simulation error: {sim_err[:200]}"

        # ── Recent history ──
        last = history[-3:] if len(history) >= 3 else history
        if last:
            progress += f"\nLast called: {' → '.join(last)}"
        # If same tool called 3x in a row, warn
        if len(last) >= 3 and len(set(last)) == 1:
            progress += f"\nWARNING: {last[0]} called 3 times with no progress. Try something else."

        # ── Ask LLM ──
        prompt = PROMPT.format(tools=tools_str, progress=progress, errors=errors)
        response = llm.invoke(prompt)
        tool = response.content.strip().strip('.').strip('"').strip()

        # ── Parse response ──
        if tool.upper() == "DONE":
            if not state.get("eval2_mutant_ratio"):
                print(f"[A] LLM said DONE, running eval first.")
                TOOLS["eval"]["fn"](state)
            break

        if tool not in TOOLS:
            print(f"[A] '{tool}' not a tool. Available: {list(TOOLS.keys())}")
            if history:
                tool = history[-1]  # fallback to last tool
                print(f"[A] Falling back to: {tool}")
            else:
                tool = "classify"

        print(f"[A] {step}: {tool}")
        history.append(tool)
        if len(history) > 10:
            history = history[-10:]

        # ── Execute ──
        try:
            result = TOOLS[tool]["fn"](state)
            state.update(result)
        except Exception as e:
            print(f"[A] Error: {e}")
            state["sim_error"] = str(e)

        # Auto-run simulate after debug or reboot (logically required)
        if tool in ("debug", "reboot") and state.get("driver_code") and state.get("checker_code"):
            print(f"[A] Auto: simulate after {tool}")
            try:
                sim_result = TOOLS["simulate"]["fn"](state)
                state.update(sim_result)
            except Exception as e:
                state["sim_error"] = str(e)

    return state
