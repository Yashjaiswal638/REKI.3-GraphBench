# GraphBench

**Topic S6.ReKI.3** — Implementation of a Graph-Based LLM Workflow for Hardware Verification

## Overview

Hardware functional verification is one of the most time-intensive stages of digital circuit design, with engineers spending approximately 49% of their time on verification tasks. Large Language Models (LLMs) present an opportunity to automate testbench generation, but ad-hoc prompting leads to unpredictable results.

This project explores a structured approach: reimplementing the [AutoBench](https://github.com/AutoBench/AutoBench) testbench generation pipeline using [LangGraph](https://github.com/langchain-ai/langgraph) to introduce modular nodes, typed state management, and controlled routing. The project also investigates using **VCD waveform data** (Value Change Dump) as additional feedback — parsing simulation waveforms into structured signal tables that an LLM can analyze to diagnose failures beyond a simple pass/fail verdict.

## Dataset & Evaluation

Uses the [VerilogEval-Human](https://github.com/NVlabs/verilog-eval) benchmark (156 problems). Evaluation follows AutoBench's framework:

| Metric | Description |
|--------|-------------|
| Eval0  | Testbench compiles without errors |
| Eval1  | Passes against the golden RTL design |
| Eval2  | Catches mutants at the same rate as the golden testbench |

## Prior Work

- **AutoBench** (Qiu et al., MLCAD 2024) — First systematic LLM-based testbench generator using a hybrid Verilog driver + Python checker
- **CorrectBench** (Qiu et al., DATE 2025) — Extended AutoBench with functional self-correction, reaching 70.13% pass ratio

## Repository Structure

```
GraphBench/
├── src/           # LangGraph pipeline implementation
├── data/          # VerilogEval-Human benchmark
├── docs/          # Papers, proposal, report
└── requirements.txt
```

## License

MIT
