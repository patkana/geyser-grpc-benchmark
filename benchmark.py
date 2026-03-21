#!/usr/bin/env python3
"""
Solana Yellowstone gRPC Benchmark Tool
Compare speed, latency, and reliability across gRPC providers.

Usage:
    pip install grpcio grpcio-tools protobuf
    python benchmark.py --endpoints "provider1=host1:port1" "provider2=host2:port2"

Example:
    python benchmark.py --endpoints "ghostgeyser=ghostgeyser.pro:10000" "helius=mainnet.helius-rpc.com:443"

Get a free trial endpoint at https://ghostgeyser.pro
"""

import grpc
import time
import sys
import os
import argparse
import socket
import threading
from collections import defaultdict

# ─── ANSI Colors ───
G = "\033[92m"; C = "\033[96m"; Y = "\033[93m"; W = "\033[97m"
D = "\033[90m"; B = "\033[1m"; R = "\033[0m"; RED = "\033[91m"
MAG = "\033[95m"

BANNER = f"""
{G}{B}  ╔═══════════════════════════════════════════════════════════╗
  ║     Solana Yellowstone gRPC Benchmark Tool                ║
  ║     Compare providers side by side                        ║
  ╚═══════════════════════════════════════════════════════════╝{R}
  {D}https://ghostgeyser.pro — Free 30-min trial available{R}
"""

# ─── Minimal Yellowstone gRPC proto (inline) ───

def build_subscribe_request():
    """Build a minimal SubscribeRequest for slots + blocks_meta"""
    def encode_varint(v):
        p = []
        while v > 0x7f:
            p.append(bytes([0x80 | (v & 0x7f)]))
            v >>= 7
        p.append(bytes([v & 0x7f]))
        return b''.join(p)

    def encode_len(fn, data):
        tag = (fn << 3) | 2
        return encode_varint(tag) + encode_varint(len(data)) + data

    def map_entry(key):
        return encode_len(1, key.encode()) + encode_len(2, b'')

    req = encode_len(2, map_entry('bench'))   # slots
    req += encode_len(3, map_entry('bench'))   # transactions
    req += encode_len(5, map_entry('bench'))   # blocks_meta
    return req


def build_account_request():
    """Build SubscribeRequest with account owner filters for DEX programs"""
    def encode_varint(v):
        p = []
        while v > 0x7f:
            p.append(bytes([0x80 | (v & 0x7f)]))
            v >>= 7
        p.append(bytes([v & 0x7f]))
        return b''.join(p)

    def encode_len(fn, data):
        tag = (fn << 3) | 2
        return encode_varint(tag) + encode_varint(len(data)) + data

    def map_entry(key, value=b''):
        entry = encode_len(1, key.encode())
        if value:
            entry += encode_len(2, value)
        return entry

    def account_filter(owner):
        return encode_len(2, owner.encode())

    req = b''
    req += encode_len(1, map_entry('orca', account_filter('whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc')))
    req += encode_len(1, map_entry('raydium', account_filter('CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C')))
    req += encode_len(1, map_entry('meteora', account_filter('LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo')))
    req += encode_len(2, map_entry('bench'))  # slots
    return req


def measure_tcp_latency(host, port, attempts=3):
    """Measure TCP connection latency"""
    times = []
    for _ in range(attempts):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            start = time.time()
            s.connect((host, int(port)))
            elapsed = (time.time() - start) * 1000
            times.append(elapsed)
            s.close()
        except Exception:
            times.append(float('inf'))
    return min(times) if times else float('inf')


class ProviderBenchmark:
    def __init__(self, name, endpoint, duration=30, use_accounts=False):
        self.name = name
        self.endpoint = endpoint
        self.duration = duration
        self.use_accounts = use_accounts
        self.total = 0
        self.accounts = 0
        self.slots = 0
        self.transactions = 0
        self.blocks = 0
        self.disconnects = 0
        self.error = None
        self.ups_samples = []
        self.latency_ms = 0

    def run(self):
        """Run benchmark for this provider"""
        host = self.endpoint.split(':')[0]
        port = self.endpoint.split(':')[1] if ':' in self.endpoint else '10000'

        # Measure TCP latency
        self.latency_ms = measure_tcp_latency(host, port)
        if self.latency_ms == float('inf'):
            self.error = "Connection failed"
            return

        # Connect gRPC
        try:
            use_ssl = int(port) == 443
            if use_ssl:
                channel = grpc.secure_channel(self.endpoint, grpc.ssl_channel_credentials(),
                    options=[('grpc.max_receive_message_length', 64 * 1024 * 1024)])
            else:
                channel = grpc.insecure_channel(self.endpoint,
                    options=[('grpc.max_receive_message_length', 64 * 1024 * 1024)])

            method = '/geyser.Geyser/Subscribe'
            multi = channel.stream_stream(method,
                request_serializer=lambda x: x,
                response_deserializer=lambda x: x)

            if self.use_accounts:
                req = build_account_request()
            else:
                req = build_subscribe_request()

            def gen():
                yield req
                time.sleep(self.duration + 10)

            start = time.time()
            last_sample = start
            last_count = 0

            for resp in multi(gen()):
                self.total += 1

                if len(resp) > 0:
                    fn = resp[0] >> 3
                    if fn == 1:
                        self.accounts += 1
                    elif fn == 2:
                        self.slots += 1
                    elif fn == 3:
                        self.transactions += 1
                    elif fn == 4 or fn == 8:
                        self.blocks += 1

                now = time.time()
                if now - last_sample >= 1.0:
                    ups = int((self.total - last_count) / (now - last_sample))
                    self.ups_samples.append(ups)
                    last_count = self.total
                    last_sample = now

                if now - start >= self.duration:
                    break

            channel.close()

        except Exception as e:
            self.error = str(e)[:80]
            self.disconnects += 1

    @property
    def avg_ups(self):
        if not self.ups_samples:
            return 0
        return int(sum(self.ups_samples) / len(self.ups_samples))

    @property
    def peak_ups(self):
        return max(self.ups_samples) if self.ups_samples else 0

    @property
    def min_ups(self):
        return min(self.ups_samples) if self.ups_samples else 0


def print_results(benchmarks):
    """Print comparison table"""
    print(f"\n{G}{B}  ═══════════════════════════════════════════════════════════{R}")
    print(f"  {W}{B}  BENCHMARK RESULTS{R}")
    print(f"{G}{B}  ═══════════════════════════════════════════════════════════{R}\n")

    # Header
    print(f"  {D}{'Provider':<20} {'Avg UPS':>10} {'Peak UPS':>10} {'Latency':>10} {'Total':>12} {'Status':>10}{R}")
    print(f"  {D}{'─' * 75}{R}")

    # Sort by avg UPS descending
    sorted_b = sorted(benchmarks, key=lambda b: b.avg_ups, reverse=True)
    winner = sorted_b[0] if sorted_b else None

    for b in sorted_b:
        if b.error:
            status = f"{RED}FAIL{R}"
            print(f"  {W}{b.name:<20}{R} {'—':>10} {'—':>10} {'—':>10} {'—':>12} {status}")
            print(f"  {RED}  Error: {b.error}{R}")
        else:
            is_winner = b == winner
            color = G if is_winner else W
            marker = f" {G}★{R}" if is_winner else ""
            lat = f"{b.latency_ms:.1f}ms"
            status = f"{G}OK{R}" if b.disconnects == 0 else f"{Y}{b.disconnects} disc{R}"

            print(f"  {color}{b.name:<20}{R} {color}{b.avg_ups:>10,}{R} {color}{b.peak_ups:>10,}{R} {color}{lat:>10}{R} {color}{b.total:>12,}{R} {status}{marker}")

    print(f"\n  {D}{'─' * 75}{R}")

    if winner and not winner.error:
        # Compare with others
        for b in sorted_b[1:]:
            if not b.error and b.avg_ups > 0:
                ratio = winner.avg_ups / b.avg_ups
                print(f"\n  {G}{B}{winner.name}{R} is {G}{B}{ratio:.1f}x faster{R} than {W}{b.name}{R}")

    print(f"\n  {D}Benchmark duration: {sorted_b[0].duration}s per provider{R}")
    print(f"  {D}Protocol: Yellowstone gRPC Subscribe{R}")

    print(f"\n{G}{B}  ═══════════════════════════════════════════════════════════{R}")
    print(f"  {Y}Get a free trial at {W}{B}https://ghostgeyser.pro{R}")
    print(f"  {D}Telegram: @GAYSER_PRIME{R}")
    print(f"{G}{B}  ═══════════════════════════════════════════════════════════{R}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Solana Yellowstone gRPC Benchmark Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare Ghost Geyser vs your Helius endpoint
  python benchmark.py --endpoints "ghostgeyser=ghostgeyser.pro:10000" "helius=your-helius:port"

  # Test a single provider for 60 seconds
  python benchmark.py --endpoints "my-provider=host:port" --duration 60

  # Test with account filters (Orca, Raydium, Meteora)
  python benchmark.py --endpoints "ghostgeyser=ghostgeyser.pro:10000" --accounts

Get a free Ghost Geyser trial at https://ghostgeyser.pro
        """
    )
    parser.add_argument('--endpoints', nargs='+', required=True,
        help='Endpoints in format "name=host:port"')
    parser.add_argument('--duration', type=int, default=30,
        help='Test duration in seconds per provider (default: 30)')
    parser.add_argument('--accounts', action='store_true',
        help='Include account owner filters (Orca, Raydium, Meteora)')

    args = parser.parse_args()

    print(BANNER)

    # Parse endpoints
    benchmarks = []
    for ep in args.endpoints:
        if '=' not in ep:
            print(f"{RED}Error: Endpoint must be in format 'name=host:port', got: {ep}{R}")
            sys.exit(1)
        name, endpoint = ep.split('=', 1)
        benchmarks.append(ProviderBenchmark(name, endpoint, args.duration, args.accounts))

    # Run benchmarks sequentially
    for i, b in enumerate(benchmarks):
        progress = f"[{i+1}/{len(benchmarks)}]"
        print(f"  {C}{progress}{R} Benchmarking {W}{B}{b.name}{R} ({b.endpoint}) for {b.duration}s...")
        sys.stdout.flush()

        b.run()

        if b.error:
            print(f"  {RED}  ✗ Failed: {b.error}{R}")
        else:
            print(f"  {G}  ✓ Done: {b.avg_ups:,} avg upd/s, {b.peak_ups:,} peak, {b.latency_ms:.1f}ms latency{R}")

        if i < len(benchmarks) - 1:
            print(f"  {D}  Cooling down 3s...{R}")
            time.sleep(3)

    # Print results
    print_results(benchmarks)


if __name__ == '__main__':
    main()
