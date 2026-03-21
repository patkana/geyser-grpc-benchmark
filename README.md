# Solana Yellowstone gRPC Benchmark Tool

Compare speed, latency, and reliability across Solana Yellowstone gRPC providers.

![benchmark](https://img.shields.io/badge/protocol-Yellowstone%20gRPC-brightgreen)
![python](https://img.shields.io/badge/python-3.8+-blue)

## What it does

This tool connects to one or more Yellowstone gRPC endpoints and measures:
- **Updates per second** (average and peak)
- **TCP latency** (connection time)
- **Total throughput** (messages received)
- **Stability** (disconnects during test)

## Quick Start

```bash
pip install grpcio protobuf
python benchmark.py --endpoints "provider1=host1:port1" "provider2=host2:port2"
```

## Examples

### Compare two providers
```bash
python benchmark.py --endpoints \
  "ghostgeyser=ghostgeyser.pro:10000" \
  "my-provider=my-host:10000"
```

### Test with DEX account filters (Orca, Raydium, Meteora)
```bash
python benchmark.py --endpoints "ghostgeyser=ghostgeyser.pro:10000" --accounts
```

### Longer test (60 seconds per provider)
```bash
python benchmark.py --endpoints "my-provider=host:port" --duration 60
```

## Sample Output

```
  ═══════════════════════════════════════════════════════════
    BENCHMARK RESULTS
  ═══════════════════════════════════════════════════════════

  Provider              Avg UPS   Peak UPS    Latency        Total     Status
  ─────────────────────────────────────────────────────────────────────────────
  ghostgeyser             23,412     41,203      2.8ms      702,360     OK ★
  other-provider           3,200      5,100     48.0ms       96,000     OK

  ghostgeyser is 7.3x faster than other-provider
```

## Requirements

- Python 3.8+
- `grpcio`
- `protobuf`

## Ghost Geyser

Need a fast Yellowstone gRPC feed? [Ghost Geyser](https://ghostgeyser.pro) offers:

- **23,000+ updates/sec** — benchmarked
- **Sub-3ms latency** — US East (Virginia)
- **Zero rate limits** — no 429 errors
- **Standard Yellowstone protocol** — drop-in replacement

**Free 30-minute trial available** — [ghostgeyser.pro](https://ghostgeyser.pro)

Telegram: [@GAYSER_PRIME](https://t.me/GAYSER_PRIME)

## License

MIT
