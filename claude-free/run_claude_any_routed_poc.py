#!/usr/bin/env python3
"""POC that exercises the real claude-any Anthropic routed path.

This script does not contact Anthropic. It starts a local Anthropic-compatible
mock upstream, configures claude-any in an isolated Anthropic routed config to
use that upstream, starts the real claude-any router, probes the router, and
optionally invokes the real `claude` CLI through that router.

The goal is to produce report-ready evidence:

* mock upstream emitted Anthropic quota/rate-limit headers;
* real claude-any routed path observed those upstream headers;
* the downstream client response from claude-any did or did not preserve them;
* real Claude Code can be launched against this routed setup.
"""

from __future__ import annotations

import argparse
import contextlib
import http.client
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CLAUDE_ANY = ROOT / "claude_any.py"
EVIDENCE_ROOT = Path(__file__).resolve().parent / "evidence"

RELEVANT_HEADERS = [
    "request-id",
    "x-request-id",
    "retry-after",
    "anthropic-ratelimit-unified-status",
    "anthropic-ratelimit-unified-reset",
    "anthropic-ratelimit-unified-5h-utilization",
    "anthropic-ratelimit-unified-5h-reset",
    "anthropic-ratelimit-unified-7d-utilization",
    "anthropic-ratelimit-unified-7d-reset",
    "anthropic-ratelimit-unified-fallback",
    "anthropic-ratelimit-unified-representative-claim",
    "anthropic-ratelimit-unified-overage-status",
    "anthropic-ratelimit-unified-overage-reset",
]


def now_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime())


def free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def sse_event(name: str, payload: dict[str, Any]) -> bytes:
    return f"event: {name}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n".encode()


def mock_body() -> bytes:
    return b"".join(
        [
            sse_event(
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg_mock_routed_001",
                        "type": "message",
                        "role": "assistant",
                        "model": "claude-mock-routed-poc",
                        "content": [],
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": {
                            "input_tokens": 111,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 0,
                            "output_tokens": 0,
                        },
                    },
                },
            ),
            sse_event(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            sse_event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "POC_OK"},
                },
            ),
            sse_event("content_block_stop", {"type": "content_block_stop", "index": 0}),
            sse_event(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 3},
                },
            ),
            sse_event("message_stop", {"type": "message_stop"}),
        ]
    )


class EvidenceLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lines: list[str] = []
        self.lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, component: str, message: str) -> None:
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        line = f"{stamp} [{component}] {message}"
        with self.lock:
            self.lines.append(line)
            self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        print(line)


class MockUpstreamHandler(BaseHTTPRequestHandler):
    server_version = "MockAnthropicRoutedPOC/1.0"
    logger: EvidenceLogger
    request_records: list[dict[str, Any]] = []

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/messages":
            self.send_error(404)
            return
        length = int(self.headers.get("content-length", "0") or 0)
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        redacted_headers = {
            key.lower(): ("[redacted]" if key.lower() in {"authorization", "x-api-key"} else value)
            for key, value in self.headers.items()
        }
        self.request_records.append(
            {
                "path": self.path,
                "headers": redacted_headers,
                "body_preview": body[:500],
            }
        )
        emitted_headers = {
            "content-type": "text/event-stream",
            "cache-control": "no-cache",
            "request-id": "req_mock_routed_001",
            "x-request-id": "xreq_mock_routed_001",
            "retry-after": "9",
            "anthropic-ratelimit-unified-status": "allowed_warning",
            "anthropic-ratelimit-unified-reset": "1780000000",
            "anthropic-ratelimit-unified-5h-utilization": "0.93",
            "anthropic-ratelimit-unified-5h-reset": "1780000000",
            "anthropic-ratelimit-unified-7d-utilization": "0.44",
            "anthropic-ratelimit-unified-7d-reset": "1780500000",
            "anthropic-ratelimit-unified-fallback": "available",
            "anthropic-ratelimit-unified-representative-claim": "five_hour",
            "anthropic-ratelimit-unified-overage-status": "allowed",
            "anthropic-ratelimit-unified-overage-reset": "1780003600",
        }
        self.logger.log(
            "MOCK-UPSTREAM",
            "received POST /v1/messages; emitting HTTP/1.1 200 OK with headers: "
            + ", ".join(f"{k}={v}" for k, v in emitted_headers.items()),
        )
        self.send_response(200)
        for name, value in emitted_headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(mock_body())
        self.wfile.flush()


@dataclass
class Probe:
    status_line: str
    headers: dict[str, str]
    usage_events: int
    body_preview: str


def parse_usage_events(body: str) -> int:
    count = 0
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if not line.startswith("data:"):
                continue
            try:
                payload = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                if isinstance(payload.get("usage"), dict):
                    count += 1
                msg = payload.get("message")
                if isinstance(msg, dict) and isinstance(msg.get("usage"), dict):
                    count += 1
    return count


def probe_router(router_port: int, logger: EvidenceLogger) -> Probe:
    body = json.dumps(
        {
            "model": "claude-any-anthropic-claude-sonnet-4-6",
            "max_tokens": 32,
            "stream": True,
            "messages": [{"role": "user", "content": "Reply POC_OK only."}],
        }
    ).encode()
    conn = http.client.HTTPConnection("127.0.0.1", router_port, timeout=20)
    conn.request(
        "POST",
        "/v1/messages",
        body=body,
        headers={
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "authorization": "Bearer mock-claude-code-oauth",
        },
    )
    resp = conn.getresponse()
    raw = resp.read().decode("utf-8", errors="replace")
    headers = {k.lower(): v for k, v in resp.getheaders()}
    relevant = {
        key: headers[key]
        for key in sorted(headers)
        if key in RELEVANT_HEADERS or key in {"content-type", "cache-control", "connection"}
    }
    status_line = f"HTTP/{resp.version // 10}.{resp.version % 10} {resp.status} {resp.reason}"
    usage_count = parse_usage_events(raw)
    logger.log(
        "ROUTER-PROBE",
        f"{status_line}; client-observed headers: "
        + ", ".join(f"{k}={v}" for k, v in relevant.items())
        + f"; usage_events={usage_count}",
    )
    conn.close()
    return Probe(status_line, relevant, usage_count, raw[:500])


def start_server(handler: type[BaseHTTPRequestHandler], port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def run_cmd(
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    logger: EvidenceLogger,
    label: str,
    timeout: float = 60,
) -> subprocess.CompletedProcess[str]:
    logger.log(label, "RUN " + " ".join(argv))
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    logger.log(label, f"EXIT rc={proc.returncode}; stdout_len={len(proc.stdout)} stderr_len={len(proc.stderr)}")
    return proc


def wait_health(port: int, timeout: float = 15) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", "/health")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            conn.close()
            if data.get("ok"):
                return data
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"router health did not become ready: {last_error}")


def parse_export_env(output: str) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("unset "):
            result[line.split(None, 1)[1]] = None
            continue
        m = re.match(r"export\s+([A-Za-z_][A-Za-z0-9_]*)=(.+)$", line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2)
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw.strip('"')
        result[key] = str(value)
    return result


def terminate_process(proc: subprocess.Popen[str] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    if os.name == "nt":
        proc.terminate()
    else:
        proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-claude", action="store_true", help="Run real `claude -p` against the local routed mock.")
    parser.add_argument("--prompt", default="Reply with POC_OK only.", help="Prompt for optional `claude -p` execution.")
    parser.add_argument("--model", default="claude-sonnet-4-6", help="Saved Anthropic model for the isolated claude-any config.")
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()

    run_dir = EVIDENCE_ROOT / f"anthropic-routed-{now_stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = EvidenceLogger(run_dir / "timeline.log")

    config_dir = run_dir / "claude-any-config"
    mock_port = free_port()
    router_port = free_port()
    mock_url = f"http://127.0.0.1:{mock_port}"

    MockUpstreamHandler.logger = logger
    MockUpstreamHandler.request_records = []
    mock_server = start_server(MockUpstreamHandler, mock_port)
    router_proc: subprocess.Popen[str] | None = None

    env = os.environ.copy()
    env["CLAUDE_ANY_CONFIG_DIR"] = str(config_dir)
    env["CLAUDE_ANY_ROUTER_PORT"] = str(router_port)

    try:
        logger.log("POC", f"run_dir={run_dir}")
        logger.log("POC", f"mock_upstream={mock_url}; router=http://127.0.0.1:{router_port}")

        setup = run_cmd(
            [
                sys.executable,
                str(CLAUDE_ANY),
                "cli",
                "--ca-provider",
                "anthropic",
                "--ca-base-url",
                mock_url,
                "--ca-model",
                args.model,
                "--ca-provider-option",
                "route_through_router=true",
                "--ca-log-level",
                "TRACE",
                "--ca-no-launch",
            ],
            ROOT,
            env,
            logger,
            "SETUP",
            timeout=30,
        )
        (run_dir / "setup.stdout.txt").write_text(setup.stdout, encoding="utf-8")
        (run_dir / "setup.stderr.txt").write_text(setup.stderr, encoding="utf-8")
        if setup.returncode != 0:
            raise RuntimeError("claude-any isolated setup failed")

        router_stdout = open(run_dir / "router.stdout.txt", "w", encoding="utf-8")
        router_stderr = open(run_dir / "router.stderr.txt", "w", encoding="utf-8")
        router_proc = subprocess.Popen(
            [sys.executable, str(CLAUDE_ANY), "serve"],
            cwd=str(ROOT),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=router_stdout,
            stderr=router_stderr,
        )
        health = wait_health(router_port)
        logger.log("ROUTER", "health=" + json.dumps(health, ensure_ascii=False, sort_keys=True))

        env_cmd = run_cmd([sys.executable, str(CLAUDE_ANY), "env"], ROOT, env, logger, "ENV", timeout=15)
        (run_dir / "claude-any-env.txt").write_text(env_cmd.stdout, encoding="utf-8")
        routed_env_delta = parse_export_env(env_cmd.stdout)
        claude_env = env.copy()
        for key, value in routed_env_delta.items():
            if value is None:
                claude_env.pop(key, None)
            else:
                claude_env[key] = value
        (run_dir / "claude-env-effective.json").write_text(
            json.dumps(
                {
                    key: ("[redacted]" if re.search("TOKEN|KEY|AUTH", key) else value)
                    for key, value in sorted(claude_env.items())
                    if key.startswith("ANTHROPIC") or key.startswith("CLAUDE")
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        probe = probe_router(router_port, logger)

        claude_result: dict[str, Any] | None = None
        if args.execute_claude:
            claude = shutil.which("claude")
            if not claude:
                raise RuntimeError("claude executable not found")
            debug_file = run_dir / "claude-debug.log"
            proc = run_cmd(
                [
                    claude,
                    "-p",
                    args.prompt,
                    "--debug",
                    "--debug-file",
                    str(debug_file),
                ],
                run_dir,
                claude_env,
                logger,
                "CLAUDE",
                timeout=args.timeout,
            )
            (run_dir / "claude.stdout.txt").write_text(proc.stdout, encoding="utf-8")
            (run_dir / "claude.stderr.txt").write_text(proc.stderr, encoding="utf-8")
            claude_result = {
                "returncode": proc.returncode,
                "stdout_preview": proc.stdout[:1000],
                "stderr_preview": proc.stderr[:1000],
                "debug_file": str(debug_file),
            }
        else:
            logger.log("CLAUDE", "skipped; rerun with --execute-claude to call real Claude Code against the local mock.")

        router_log = config_dir / "router.log"
        copied_router_log = run_dir / "router.log"
        if router_log.exists():
            copied_router_log.write_text(router_log.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")

        evidence = {
            "purpose": "Exercise real claude-any Anthropic routed path with local mock upstream and optional real Claude Code invocation.",
            "run_dir": str(run_dir),
            "mock_upstream": mock_url,
            "router_url": f"http://127.0.0.1:{router_port}",
            "router_health": health,
            "router_probe": asdict(probe),
            "mock_requests": MockUpstreamHandler.request_records,
            "claude_executed": bool(args.execute_claude),
            "claude_result": claude_result,
            "assertions": {
                "mock_upstream_was_called": bool(MockUpstreamHandler.request_records),
                "router_probe_saw_usage_events": probe.usage_events > 0,
                "router_probe_lost_anthropic_quota_headers": not any(
                    key.startswith("anthropic-ratelimit-") for key in probe.headers
                ),
                "router_probe_lost_request_id": "request-id" not in probe.headers and "x-request-id" not in probe.headers,
            },
        }
        (run_dir / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        failed = [key for key, ok in evidence["assertions"].items() if not ok]
        logger.log("POC", "ASSERTIONS " + ("PASS" if not failed else "FAIL " + ",".join(failed)))
        print()
        print(f"Evidence directory: {run_dir}")
        return 1 if failed else 0
    finally:
        terminate_process(router_proc)
        mock_server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())

