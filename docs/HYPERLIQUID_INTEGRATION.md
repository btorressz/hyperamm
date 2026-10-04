# Hyperliquid Integration

HyperAMM targets the official `hyperliquid-python-sdk` and pins the Phase 1–4 compatibility range to `>=0.24.0,<0.25`. The integration boundary is intentionally narrow so SDK payload changes do not propagate through strategy or frontend code.

## Public market data

`HyperliquidMarketDataAdapter` constructs `Info` against the main public API and subscribes to `{"type":"l2Book","coin":market}`. It also requests an initial `l2_snapshot`. The adapter normalizes SDK `levels` (`px`, `sz`, `n`) into `MarketLevel` and `OrderBookSnapshot`, tracks the exchange millisecond timestamp, and rejects older updates rather than allowing them to overwrite newer state.

If initialization/subscription fails, the service reports an unavailable/degraded LIVE state. It never invents a live price and never silently falls back to demo data. Demo mode is separately and visibly labeled `SIMULATED DEMO DATA`.

## Testnet execution

`HyperliquidTestnetExecutionAdapter` uses the SDK `Exchange` client only after all guards pass. Limit liquidity is submitted using `Exchange.order(...)` with `Alo` (add-liquidity-only/post-only) and a deterministic 16-byte `Cloid`. Cancellation uses `cancel_by_cloid`.

Signed order transmission requires all of:

```text
EXECUTION_MODE=TESTNET
ENABLE_HYPERLIQUID_TESTNET_ORDERS=true
HYPERLIQUID_PRIVATE_KEY=<testnet signing key>
```

The default is PAPER and the guard is checked before a signing client is created. No mainnet execution adapter exists. Withdrawals, transfers and bridging are not implemented.

## Security assumptions

Signing material exists only in backend environment variables. React never receives it. `.env` is ignored. The code never logs the private key. Public LIVE market data requires no wallet.

## Known Phase 1–4 limitations

The project does not implement inventory skew, volatility/book-imbalance adaptation, perp funding-aware vAMM logic, external oracle protection, full institutional risk policy, AI agents, strategy optimization, vault accounting or mainnet execution. Those are roadmap items rather than hidden placeholders.
