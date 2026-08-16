# REKI.3 GraphBench

**Topic S6.ReKI.3** — An LLM-Agent Workflow for Hardware Verification

## Overview

Hardware functional verification is one of the most time-intensive stages of digital circuit design. REKI.3 reimplements the [AutoBench](https://github.com/AutoBench/AutoBench) testbench-generation pipeline as an **autonomous LLM agent on [LangGraph](https://github.com/langchain-ai/langgraph)**: the AutoBench stages are exposed as 15 guarded tools, and the LLM itself decides which tool to run and when. The project also introduces **VCD waveform diagnosis** — parsing simulation waveforms into signal tables that the LLM analyzes to find the root cause of a failure, beyond a binary pass/fail verdict.

## Architecture

```
python -m reki3.run_benchmark
        ↓
agent_loop()  →  LangGraph StateGraph (3 nodes)
        ↓
START → agent (LLM picks one tool) ⇄ ToolNode (executes it) → finalize (eval) → END
        ↓
15 tools = AutoBench stages (classify, spec, scenarios, rules, driver_cmb/seq,
checklist, stage4b, checker_cmb/seq, simulate, debug, analyze_waveform, reboot, eval)
with deterministic guards (prerequisites, debug/reboot budgets, timeouts)
```

- **LLM**: DeepSeek (`deepseek-coder`) via `ChatOpenAI`, temperature 0
- **Tools**: LangChain `@tool` wrappers around the verbatim AutoBench prompt pipeline (`src/reki3/core/`)
- **State**: typed `AgentState` channels. Two bridges, selected by env key `REKI3_STATE_BRIDGE`:
  - `shared` (default) — shared mutable dict + write-back echo
  - `injected` — LangGraph-native `InjectedState` + `Command(update=…)`
- **VCD diagnosis**: `$dumpfile`/`$dumpvars` in drivers → `vcdvcd` parsing → LLM root-cause diagnosis fed into the next debug fix

## Dataset & Evaluation

[VerilogEval-Human](https://github.com/NVlabs/verilog-eval) (156 HDLBits problems). Metrics follow AutoBench:

| Metric | Description |
|--------|-------------|
| Eval0  | Testbench compiles without errors |
| Eval1  | Passes against the golden RTL design |
| Eval2  | Catches mutants at the same rate as the golden testbench (verdict parity, R = 0.8) |
| Eval2b | Same parity check against GPT-generated RTL |

## Repository Structure

```
REKI.3-GraphBench/
├── src/reki3/
│   ├── run_benchmark.py   # entry point (resume-capable benchmark runner)
│   ├── core/              # AutoBench reimplementation: node functions, prompts, verilog utils
│   ├── plumbing/          # LLM router, iverilog/vvp, python, subprocess wrappers
│   └── agent/             # LangGraph agent: graph, agent node, tools, state
├── scripts/               # results analysis (pass rates, pass@k)
├── config/                # model configuration
├── data/HDLBits/          # 156-problem benchmark, mutants, GPT-generated RTL
├── docs/                  # proposal, technical explanation, file map
├── results/               # benchmark results (JSON)
└── requirements.txt
```

## Setup & Usage (WSL)

```bash
python -m venv ~/reki3-venv
source ~/reki3-venv/bin/activate
pip install -r requirements.txt
# iverilog required: sudo apt install iverilog

cd /mnt/d/Projects/REKI.3-GraphBench/src
python -m reki3.run_benchmark                        # full benchmark (resumes from results/)
REKI3_STATE_BRIDGE=injected python -m reki3.run_benchmark   # LangGraph-native state bridge
```

## Prior Work

- **AutoBench** (Qiu et al., MLCAD 2024) — first systematic LLM-based testbench generator (hybrid Verilog driver + Python checker)
- **CorrectBench** (Qiu et al., DATE 2025) — extended AutoBench with functional self-correction (70.13% pass ratio)

## License

MIT
