"""Compare time-to-first-token with total time, to detect response buffering.

Start the stack with DWARPAL_MOCK_DELAY_MS=300 so the mock sends one word every 300 ms.
If a proxy buffers the stream, the first token arrives about when the last one does.
"""
import argparse
import sys
import time

import httpx


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--key", required=True)
    args = p.parse_args()

    body = {
        "model": "auto",
        "stream": True,
        "messages": [{"role": "user", "content": "one two three four five six"}],
    }
    headers = {"Authorization": f"Bearer {args.key}", "X-Dwarpal-Cache": "bypass"}
    start = time.perf_counter()
    first = None
    with httpx.stream(
        "POST", f"{args.base_url}/v1/chat/completions", json=body, headers=headers, timeout=60
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if first is None and line.startswith("data: ") and '"content"' in line:
                first = time.perf_counter() - start
    total = time.perf_counter() - start

    if first is None:
        print("FAIL: no content chunk received")
        return 1
    print(f"time to first token: {first:.2f}s | total: {total:.2f}s | ratio: {first / total:.2f}")
    if first > 0.6 * total:
        print("FAIL: looks buffered (first token arrived near the end)")
        return 1
    print("OK: tokens are streaming")
    return 0


if __name__ == "__main__":
    sys.exit(main())