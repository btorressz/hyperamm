# HyperAMM — Project Summary

> Adaptive virtual AMM, market-making, risk, simulation, accounting, and operator-terminal research system for Hyperliquid.

---

## 🚀 Overview

HyperAMM is a research-focused market-making infrastructure project built with:

- **Python 3.12**
- **FastAPI**
- **React**
- **TypeScript**
- **Hyperliquid Python SDK**

The project explores how AMM-style liquidity models can be adapted to operate over Hyperliquid's central-limit-order-book structure.

Rather than deploying a traditional on-chain AMM directly, HyperAMM internally models liquidity using AMM mathematics and then compiles that desired liquidity into executable CLOB bid/ask levels.

The system evolved through twelve major phases from basic Hyperliquid market data and PAPER execution into a much broader trading infrastructure stack containing:

- virtual constant-product AMM modeling
- concentrated liquidity
- inventory-aware quoting
- volatility adaptation
- order-book imbalance adaptation
- perpetual-market context
- multi-source reference-price validation
- deterministic institutional risk controls
- supervisory trading agents
- strategy simulation and optimization
- deterministic vault/accounting
- a full React trading and liquidity terminal

The system remains intentionally focused on:

**PAPER execution + guarded TESTNET research**

and does **not** claim production-mainnet readiness.

# 🧠 Core Design Philosophy

HyperAMM separates:

```text
Strategy
    from
Risk
    from
Execution
    from
Accounting
    from
Observability

The system is designed so that increasingly intelligent strategy components can propose changes without becoming the final authority over execution.

---
