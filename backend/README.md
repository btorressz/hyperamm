# HyperAMM Backend

FastAPI backend for HyperAMM Phases 1–4. It separates normalized market data, AMM mathematics, quote compilation, risk, and execution. The default configuration is `DEMO` market data + `PAPER` execution so no wallet is required.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
pytest
uvicorn app.main:app --reload
```

Public live Hyperliquid market data can be enabled with `MARKET_DATA_MODE=LIVE`. Signed testnet execution additionally requires `EXECUTION_MODE=TESTNET`, `ENABLE_HYPERLIQUID_TESTNET_ORDERS=true`, and a testnet signing key supplied through environment variables. Mainnet execution is intentionally absent.
