# """LLM Agent — LLM autonomously selects tools. Code only enforces hard safety limits."""
# from pipeline.tools import TOOLS
# from pipeline.graph import get_llm

# PROMPT = """Tools: {tools}

# Progress: {progress}

# Errors: {errors}

# Pick ONE tool. Reply with only the tool name."""  # No "DONE" — eval means done


# def agent_loop(initial_state, max_steps=30):
#     state = dict(initial_state)
#     llm = get_llm()
#     history = []

#     for step in range(max_steps):
#         # ── Hard safety limits ──
#         if state.get("eval2_mutant_ratio", ""):
#             break
#         d = state.get("debug_iter", 0)
#         MAX_DEBUG = 3
#         if d >= MAX_DEBUG:
#             if not state.get("eval2_mutant_ratio"):
#                 print(f"[A] Debug exhausted (d={d}), forcing eval.")
#                 TOOLS["eval"]["fn"](state)
#             break

#         # ── Build tool list with descriptions ──
#         tools_str = "\n".join(f"  {n}: {t['desc']}" for n, t in TOOLS.items())

#         # ── Build progress summary (DONE first, then what's MISSING) ──
#         ct = state.get("circuit_type", "?")
#         done = []
#         missing = []
#         if ct and ct != "?":
#             done.append(f"classified as {ct}")
#         else:
#             missing.append("classify (unknown circuit type)")
#         if state.get("spec"):
#             done.append("spec ready")
#         else:
#             missing.append("spec (no specification)")
#         if state.get("scenarios"):
#             done.append("scenarios ready")
#         else:
#             missing.append("scenarios (no test plan)")
#         if state.get("golden_rules"):
#             done.append("rules ready")
#         else:
#             missing.append("rules (no golden reference)")
#         if state.get("driver_code"):
#             done.append("driver ready")
#         else:
#             missing.append("driver (no Verilog testbench)")
#         if state.get("checker_code"):
#             done.append("checker ready")
#         else:
#             # Auto-insert checklist if driver exists but checklist wasn't called
#             if state.get("driver_code") and not state.get("checker_code"):
#                 if "checklist" not in [h for h in history[-5:] if h]:
#                     missing.append("checklist (verify driver coverage first!)")
#             missing.append("checker (no Python validator)")
#         if state.get("driver_code") and state.get("checker_code") and not state.get("sim_passed") and d == 0:
#             done.append("READY TO SIMULATE")
#         if state.get("waveform_analysis") and state["waveform_analysis"] != "placeholder":
#             done.append("diagnosis ready")
#         if state.get("sim_passed"):
#             state.pop("_diagnosed", None)  # clear for next failure
#             done.append("simulation PASSED")
#         elif d > 0:
#             done.append(f"simulation FAILED (debug={d})")

#         progress = "DONE: " + (", ".join(done) if done else "nothing yet")
#         if missing:
#             progress += "\nMISSING: " + ", ".join(missing)
#         if ct and ct != "?":
#             progress += f"\nCircuit type: {ct} — use {'driver_cmb/checker_cmb' if ct == 'CMB' else 'driver_seq/stage4b/checker_seq'}"

#         # ── Build error context ──
#         errors = ""
#         sim_err = state.get("sim_error", "")
#         if sim_err and not state.get("sim_passed"):
#             errors = f"Last simulation error: {sim_err[:200]}"

#         # ── Recent history ──
#         last = history[-3:] if len(history) >= 3 else history
#         if last:
#             progress += f"\nLast called: {' → '.join(last)}"
#         # If same tool called 3x in a row, warn
#         if len(last) >= 3 and len(set(last)) == 1:
#             progress += f"\nWARNING: {last[0]} called 3 times with no progress. Try something else."

#         # ── Ask LLM ──
#         prompt = PROMPT.format(tools=tools_str, progress=progress, errors=errors)
#         response = llm.invoke(prompt)
#         tool = response.content.strip().strip('.').strip('"').strip()

#         # ── Parse response ──
#         if tool.upper() == "DONE":
#             if not state.get("eval2_mutant_ratio"):
#                 print(f"[A] LLM said DONE, running eval first.")
#                 TOOLS["eval"]["fn"](state)
#             break

#         if tool not in TOOLS:
#             print(f"[A] '{tool}' not a tool. Available: {list(TOOLS.keys())}")
#             if history:
#                 tool = history[-1]  # fallback to last tool
#                 print(f"[A] Falling back to: {tool}")
#             else:
#                 tool = "classify"

#         print(f"[A] {step}: {tool}")
#         history.append(tool)
#         if len(history) > 10:
#             history = history[-10:]

#         # ── Execute ──
#         try:
#             result = TOOLS[tool]["fn"](state)
#             state.update(result)
#         except Exception as e:
#             print(f"[A] Error: {e}")
#             state["sim_error"] = str(e)

#         # Auto-run simulate after debug/reboot (logically required)
#         if tool in ("debug", "reboot") and state.get("driver_code") and state.get("checker_code"):
#             print(f"[A] Auto: simulate after {tool}")
#             try:
#                 sim_result = TOOLS["simulate"]["fn"](state)
#                 state.update(sim_result)
#             except Exception as e:
#                 state["sim_error"] = str(e)

#         # Flow: debug(0) → debug(1) → diagnose → debug(2) → eval
#         d = state.get("debug_iter", 0)
#         if d == 2 and not state.get("sim_passed") and state.get("sim_error"):
#             if not state.get("_diagnosed"):
#                 print(f"[A] d=2: diagnose → debug → simulate")
#                 state["_diagnosed"] = True
#                 try:
#                     diag = TOOLS["diagnose"]["fn"](state)
#                     state.update(diag)
#                     dbg = TOOLS["debug"]["fn"](state)
#                     state.update(dbg)
#                     sim = TOOLS["simulate"]["fn"](state)
#                     state.update(sim)
#                 except Exception as e:
#                     state["sim_error"] = str(e)

#     return state


# # """LLM Agent — LLM autonomously selects tools.
# # Code only enforces hard safety limits and recovery policies.
# # """

# # from pathlib import Path
# # import json

# # from pipeline.tools import TOOLS
# # from pipeline.graph import get_llm


# # PROMPT = """Tools: {tools}

# # Progress: {progress}

# # Errors: {errors}

# # Pick ONE tool. Reply with only the tool name."""  # No "DONE" — eval means done


# # MAX_DEBUG = 3


# # # ---------------------------------------------------------------------------
# # # Progress / prompt helpers
# # # ---------------------------------------------------------------------------

# # def build_progress(state, history):
# #     ct = state.get("circuit_type", "?")
# #     done = []
# #     missing = []

# #     if ct and ct != "?":
# #         done.append(f"classified as {ct}")
# #     else:
# #         missing.append("classify (unknown circuit type)")

# #     if state.get("spec"):
# #         done.append("spec ready")
# #     else:
# #         missing.append("spec (no specification)")

# #     if state.get("scenarios"):
# #         done.append("scenarios ready")
# #     else:
# #         missing.append("scenarios (no test plan)")

# #     if state.get("golden_rules"):
# #         done.append("rules ready")
# #     else:
# #         missing.append("rules (no golden reference)")

# #     if state.get("driver_code"):
# #         done.append("driver ready")
# #     else:
# #         missing.append("driver (no Verilog testbench)")

# #     if state.get("checker_code"):
# #         done.append("checker ready")
# #     else:
# #         if state.get("driver_code") and not state.get("checker_code"):
# #             if "checklist" not in [h for h in history[-5:] if h]:
# #                 missing.append("checklist (verify driver coverage first!)")
# #         missing.append("checker (no Python validator)")

# #     d = state.get("debug_iter", 0)

# #     if (
# #         state.get("driver_code")
# #         and state.get("checker_code")
# #         and not state.get("sim_passed")
# #         and d == 0
# #     ):
# #         done.append("READY TO SIMULATE")

# #     if (
# #         state.get("waveform_analysis")
# #         and state["waveform_analysis"] != "placeholder"
# #     ):
# #         done.append("diagnosis ready")

# #     if state.get("sim_passed"):
# #         state.pop("_diagnosed", None)
# #         done.append("simulation PASSED")
# #     elif d > 0:
# #         done.append(f"simulation FAILED (debug={d})")

# #     progress = "DONE: " + (", ".join(done) if done else "nothing yet")

# #     if missing:
# #         progress += "\nMISSING: " + ", ".join(missing)

# #     if ct and ct != "?":
# #         next_hint = (
# #             "driver_cmb/checker_cmb"
# #             if ct == "CMB"
# #             else "driver_seq/stage4b/checker_seq"
# #         )
# #         progress += f"\nCircuit type: {ct} — use {next_hint}"

# #     last = history[-3:] if len(history) >= 3 else history

# #     if last:
# #         progress += f"\nLast called: {' → '.join(last)}"

# #     if len(last) >= 3 and len(set(last)) == 1:
# #         progress += (
# #             f"\nWARNING: {last[0]} called 3 times with no progress. Try something else."
# #         )

# #     return progress


# # def build_error_context(state):
# #     sim_err = state.get("sim_error", "")

# #     if sim_err and not state.get("sim_passed"):
# #         return f"Last simulation error: {sim_err[:200]}"

# #     return ""


# # # ---------------------------------------------------------------------------
# # # Planner helper
# # # ---------------------------------------------------------------------------

# # def choose_tool(llm, state, history):
# #     tools_str = "\n".join(
# #         f"  {n}: {t['desc']}" for n, t in TOOLS.items()
# #     )

# #     progress = build_progress(state, history)
# #     errors = build_error_context(state)

# #     prompt = PROMPT.format(
# #         tools=tools_str,
# #         progress=progress,
# #         errors=errors,
# #     )

# #     response = llm.invoke(prompt)

# #     # Safer parsing: use first non-empty line only
# #     lines = [ln.strip() for ln in response.content.splitlines() if ln.strip()]
# #     tool = lines[0] if lines else ""
# #     tool = tool.strip().strip('.').strip('"').strip()

# #     if tool.upper() == "DONE":
# #         return "DONE"

# #     if tool not in TOOLS:
# #         print(f"[A] '{tool}' not a tool. Available: {list(TOOLS.keys())}")
# #         if history:
# #             tool = history[-1]
# #             print(f"[A] Falling back to: {tool}")
# #         else:
# #             tool = "classify"

# #     return tool


# # # ---------------------------------------------------------------------------
# # # Execution helpers
# # # ---------------------------------------------------------------------------

# # def execute_tool(tool, state):
# #     result = TOOLS[tool]["fn"](state)

# #     if result:
# #         state.update(result)


# # def auto_simulate_after_repair(tool, state):
# #     if (
# #         tool in ("debug", "reboot")
# #         and state.get("driver_code")
# #         and state.get("checker_code")
# #     ):
# #         print(f"[A] Auto: simulate after {tool}")

# #         sim_result = TOOLS["simulate"]["fn"](state)

# #         if sim_result:
# #             state.update(sim_result)


# # def maybe_run_diagnose_flow(state):
# #     d = state.get("debug_iter", 0)

# #     if d == 2 and not state.get("sim_passed") and state.get("sim_error"):
# #         if not state.get("_diagnosed"):
# #             print("[A] d=2: diagnose → debug → simulate")

# #             state["_diagnosed"] = True

# #             diag = TOOLS["diagnose"]["fn"](state)
# #             if diag:
# #                 state.update(diag)

# #             dbg = TOOLS["debug"]["fn"](state)
# #             if dbg:
# #                 state.update(dbg)

# #             sim = TOOLS["simulate"]["fn"](state)
# #             if sim:
# #                 state.update(sim)


# # # ---------------------------------------------------------------------------
# # # Main agent loop
# # # ---------------------------------------------------------------------------

# # def agent_loop(initial_state, max_steps=30):
# #     state = dict(initial_state)
# #     llm = get_llm()

# #     history = []
# #     trace = []

# #     for step in range(max_steps):

# #         # Hard safety limits
# #         if state.get("eval2_mutant_ratio", ""):
# #             break

# #         d = state.get("debug_iter", 0)

# #         if d >= MAX_DEBUG:
# #             if not state.get("eval2_mutant_ratio"):
# #                 print(f"[A] Debug exhausted (d={d}), forcing eval.")
# #                 execute_tool("eval", state)
# #             break

# #         # Ask LLM which tool to use next
# #         tool = choose_tool(llm, state, history)

# #         if tool == "DONE":
# #             if not state.get("eval2_mutant_ratio"):
# #                 print("[A] LLM said DONE, running eval first.")
# #                 execute_tool("eval", state)
# #             break

# #         print(f"[A] {step}: {tool}")

# #         history.append(tool)
# #         history = history[-10:]

# #         try:
# #             execute_tool(tool, state)
# #             auto_simulate_after_repair(tool, state)
# #             maybe_run_diagnose_flow(state)

# #         except Exception as e:
# #             print(f"[A] Error: {e}")
# #             state["sim_error"] = str(e)

# #         # Trace for reproducibility
# #         trace.append(
# #             {
# #                 "step": step,
# #                 "tool": tool,
# #                 "debug_iter": state.get("debug_iter", 0),
# #                 "sim_passed": state.get("sim_passed"),
# #                 "eval2": state.get("eval2_mutant_ratio", ""),
# #             }
# #         )

# #     # Save execution trace
# #     try:
# #         run_dir = Path("../runs") / state["task_id"]
# #         run_dir.mkdir(parents=True, exist_ok=True)

# #         (run_dir / "trace.json").write_text(
# #             json.dumps(trace, indent=2)
# #         )
# #     except Exception as e:
# #         print(f"[A] Warning: failed to save trace: {e}")

# #     return state

"""LLM Agent — LLM autonomously selects tools.
Code only enforces hard safety limits and recovery policies.
"""

from pathlib import Path
import json

from pipeline.tools import TOOLS
from pipeline.graph import get_llm


PROMPT = """Tools: {tools}

Progress: {progress}

Errors: {errors}

Pick ONE tool. Reply with only the tool name."""


MAX_DEBUG = 3


# ---------------------------------------------------------------------------
# Progress / prompt helpers
# ---------------------------------------------------------------------------

def build_progress(state, history):
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
        if state.get("driver_code") and not state.get("checker_code"):
            if "checklist" not in [h for h in history[-5:] if h]:
                missing.append("checklist (verify driver coverage first!)")
        missing.append("checker (no Python validator)")

    d = state.get("debug_iter", 0)

    if (
        state.get("driver_code")
        and state.get("checker_code")
        and not state.get("sim_passed")
        and d == 0
    ):
        done.append("READY TO SIMULATE")

    if (
        state.get("waveform_analysis")
        and state["waveform_analysis"] != "placeholder"
    ):
        done.append("diagnosis ready")

    if state.get("sim_passed"):
        state.pop("_diagnosed", None)
        done.append("simulation PASSED")
    elif d > 0:
        done.append(f"simulation FAILED (debug={d})")

    progress = "DONE: " + (", ".join(done) if done else "nothing yet")

    if missing:
        progress += "\nMISSING: " + ", ".join(missing)

    if ct and ct != "?":
        next_hint = (
            "driver_cmb/checker_cmb"
            if ct == "CMB"
            else "driver_seq/stage4b/checker_seq"
        )
        progress += f"\nCircuit type: {ct} — use {next_hint}"

    last = history[-3:] if len(history) >= 3 else history

    if last:
        progress += f"\nLast called: {' → '.join(last)}"

    if len(last) >= 3 and len(set(last)) == 1:
        progress += (
            f"\nWARNING: {last[0]} called 3 times with no progress. Try something else."
        )

    return progress


def build_error_context(state):
    sim_err = state.get("sim_error", "")

    if sim_err and not state.get("sim_passed"):
        return f"Last simulation error: {sim_err[:200]}"

    return ""


# ---------------------------------------------------------------------------
# Planner helper
# ---------------------------------------------------------------------------

def choose_tool(llm, state, history):
    tools_str = "\n".join(
        f"  {n}: {t['desc']}" for n, t in TOOLS.items()
    )

    progress = build_progress(state, history)
    errors = build_error_context(state)

    prompt = PROMPT.format(
        tools=tools_str,
        progress=progress,
        errors=errors,
    )

    response = llm.invoke(prompt)

    # IMPORTANT: restore original parsing behavior exactly
    tool = response.content.strip().strip('.').strip('"').strip()

    if tool.upper() == "DONE":
        return "DONE"

    if tool not in TOOLS:
        print(f"[A] '{tool}' not a tool. Available: {list(TOOLS.keys())}")
        if history:
            tool = history[-1]
            print(f"[A] Falling back to: {tool}")
        else:
            tool = "classify"

    return tool


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------

def execute_tool(tool, state):
    result = TOOLS[tool]["fn"](state)

    if result:
        state.update(result)


def auto_simulate_after_repair(tool, state):
    if (
        tool in ("debug", "reboot")
        and state.get("driver_code")
        and state.get("checker_code")
    ):
        print(f"[A] Auto: simulate after {tool}")

        sim_result = TOOLS["simulate"]["fn"](state)

        if sim_result:
            state.update(sim_result)


# ---------------------------------------------------------------------------
# Compile-error detection
# ---------------------------------------------------------------------------

def is_compile_error(state):
    err = (state.get("sim_error") or "").lower()

    compile_markers = [
        "syntax error",
        "unable to bind",
        "undeclared",
        "undefined macro",
        "invalid module",
        "parse error",
        "expecting",
        "compilation error",
    ]

    return any(marker in err for marker in compile_markers)


# ---------------------------------------------------------------------------
# Diagnose escalation helper
# ---------------------------------------------------------------------------

def maybe_run_diagnose_flow(state):
    d = state.get("debug_iter", 0)

    # NEW FIX: do not run VCD diagnosis for compile errors
    if is_compile_error(state):
        return

    if d == 2 and not state.get("sim_passed") and state.get("sim_error"):
        if not state.get("_diagnosed"):
            print("[A] d=2: diagnose → debug → simulate")

            state["_diagnosed"] = True

            diag = TOOLS["diagnose"]["fn"](state)
            if diag:
                state.update(diag)

            dbg = TOOLS["debug"]["fn"](state)
            if dbg:
                state.update(dbg)

            sim = TOOLS["simulate"]["fn"](state)
            if sim:
                state.update(sim)


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

def agent_loop(initial_state, max_steps=30):
    state = dict(initial_state)
    llm = get_llm()

    history = []
    trace = []

    for step in range(max_steps):

        # Hard safety limits
        if state.get("eval2_mutant_ratio", ""):
            break

        d = state.get("debug_iter", 0)

        if d >= MAX_DEBUG:
            if not state.get("eval2_mutant_ratio"):
                print(f"[A] Debug exhausted (d={d}), forcing eval.")
                execute_tool("eval", state)
            break

        # Ask LLM which tool to use next
        tool = choose_tool(llm, state, history)

        if tool == "DONE":
            if not state.get("eval2_mutant_ratio"):
                print("[A] LLM said DONE, running eval first.")
                execute_tool("eval", state)
            break

        print(f"[A] {step}: {tool}")

        history.append(tool)
        history = history[-10:]

        try:
            execute_tool(tool, state)
            auto_simulate_after_repair(tool, state)
            maybe_run_diagnose_flow(state)

        except Exception as e:
            print(f"[A] Error: {e}")
            state["sim_error"] = str(e)

        # Trace for reproducibility
        trace.append(
            {
                "step": step,
                "tool": tool,
                "debug_iter": state.get("debug_iter", 0),
                "sim_passed": state.get("sim_passed"),
                "eval2": state.get("eval2_mutant_ratio", ""),
            }
        )

    # Save execution trace (best effort)
    try:
        run_dir = Path("../runs") / state["task_id"]
        run_dir.mkdir(parents=True, exist_ok=True)

        (run_dir / "trace.json").write_text(
            json.dumps(trace, indent=2)
        )
    except Exception:
        pass

    return state