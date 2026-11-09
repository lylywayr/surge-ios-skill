#!/usr/bin/env python3
"""Test one temporary Surge policy descriptor without changing the profile.

Runs a cron-type script through the External Controller (`script evaluate`, same as
surge-cli) whose $httpClient request carries the full policy line as `policy-descriptor`.
The descriptor is sent in memory only: no temp file, never printed.
"""

import argparse
import base64
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import surge_cli  # noqa: E402


def redact(text: str) -> str:
    return re.sub(
        r"(?i)(password|psk|username|private-key|token)\s*=\s*([^,\s]+)",
        r"\1=<redacted>",
        text,
    )


def read_descriptor(path: str) -> str:
    if path == "-":
        raw = sys.stdin.read()
    else:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) != 1 or "=" not in lines[0]:
        raise ValueError("descriptor input must contain exactly one non-empty Surge policy line")
    return lines[0]


def main() -> int:
    p = argparse.ArgumentParser(description="Test an unconfigured node via surge-cli script evaluate + policy-descriptor.")
    p.add_argument("--descriptor-file", default="-", help="one Surge policy line; default: stdin")
    p.add_argument("--remote", "-r", default=surge_cli.DEFAULT_REMOTE, help="controller host:port (default 127.0.0.1:6170)")
    p.add_argument("--url", default="http://checkip.amazonaws.com", help="HTTP(S) probe URL")
    p.add_argument("--timeout", type=float, default=12, help="probe timeout in seconds")
    args = p.parse_args()

    if not os.environ.get("SURGE_CLI_PASSWORD"):
        p.error("SURGE_CLI_PASSWORD is not set")
    if args.timeout <= 0:
        p.error("--timeout must be positive")
    try:
        descriptor = read_descriptor(args.descriptor_file)
    except (OSError, ValueError) as e:
        p.error(str(e))

    name = descriptor.split("=", 1)[0].strip()
    options = {"url": args.url, "timeout": args.timeout, "policy-descriptor": descriptor}
    script = (
        "const started = Date.now();\n"
        f"$httpClient.get({json.dumps(options)}, (error, response, data) => {{\n"
        "  $done({error, status: response && response.status, data, "
        "latency: Date.now() - started});\n"
        "});"
    )
    b64 = base64.b64encode(script.encode()).decode()
    # mock type 3 = cron (see surge_cli.normalize)
    argv = ["script", "evaluate", b64, "3", str(int(args.timeout + 3))]

    c = surge_cli.Controller(args.remote, surge_cli.credential(False), timeout=args.timeout + 10)
    try:
        c.send(argv)
        payload = c.read_one()
    finally:
        c.close()

    if isinstance(payload, dict) and payload.get("error"):
        print(json.dumps({"node": name, "controller_error": redact(str(payload["error"]))}, ensure_ascii=False))
        return 1
    result = payload.get("result", payload) if isinstance(payload, dict) else payload
    if not isinstance(result, dict):
        print(json.dumps({"node": name, "unexpected": redact(json.dumps(payload, ensure_ascii=False))}, ensure_ascii=False))
        return 1
    print(redact(json.dumps({"node": name, "result": result}, ensure_ascii=False, indent=2)))
    try:
        ok = not result.get("error") and 200 <= int(result.get("status") or 0) < 400
    except (TypeError, ValueError):
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
