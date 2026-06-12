#!/usr/bin/env python3
"""Local POC for Anthropic-compatible proxy header loss.

This script is intentionally self-contained and calls no external services.
It starts a mock Anthropic upstream and two proxy modes:

* strip   - mimics a proxy that forwards SSE but drops quota headers.
* forward - forwards a safe subset of upstream headers.

The output shows whether client-visible quota/rate-limit headers survive while
SSE usage events remain available.
"""

from __future__ import annotations

import argparse
import contextlib
import http.client
import json
import socket
import threading
import time
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen


EVENT_LOG: list[str] = []
EVENT_LOG_LOCK = threading.Lock()


def log_event(component: str, message: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    line = f"{stamp} [{component}] {message}"
    with EVENT_LOG_LOCK:
        EVENT_LOG.append(line)
    print(line)


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
    "anthropic-ratelimit-unified-overage-disabled-reason",
]

HOP_BY_HOP_HEADERS = {
    "connection",
    "transfer-encoding",
    "content-length",
    "content-encoding",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "upgrade",
}


def free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def sse_event(name: str, payload: dict) -> bytes:
    return f"event: {name}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n".encode(
        "utf-8"
    )


def mock_sse_body() -> bytes:
    chunks = [
        sse_event(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_mock_001",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-mock-poc",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {
                        "input_tokens": 123,
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
                "delta": {"type": "text_delta", "text": "POC OK"},
            },
        ),
        sse_event("content_block_stop", {"type": "content_block_stop", "index": 0}),
        sse_event(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": 5},
            },
        ),
        sse_event("message_stop", {"type": "message_stop"}),
    ]
    return b"".join(chunks)


class MockAnthropicHandler(BaseHTTPRequestHandler):
    server_version = "MockAnthropicPOC/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/messages":
            self.send_error(404)
            return
        length = int(self.headers.get("content-length", "0") or 0)
        _ = self.rfile.read(length)

        emitted_headers = {
            "content-type": "text/event-stream",
            "cache-control": "no-cache",
            "request-id": "req_mock_header_001",
            "x-request-id": "xreq_mock_header_001",
            "retry-after": "7",
            "anthropic-ratelimit-unified-status": "allowed_warning",
            "anthropic-ratelimit-unified-reset": "1780000000",
            "anthropic-ratelimit-unified-5h-utilization": "0.91",
            "anthropic-ratelimit-unified-5h-reset": "1780000000",
            "anthropic-ratelimit-unified-7d-utilization": "0.42",
            "anthropic-ratelimit-unified-7d-reset": "1780500000",
            "anthropic-ratelimit-unified-fallback": "available",
            "anthropic-ratelimit-unified-representative-claim": "five_hour",
            "anthropic-ratelimit-unified-overage-status": "allowed",
            "anthropic-ratelimit-unified-overage-reset": "1780003600",
        }
        log_event(
            "UPSTREAM",
            "HTTP/1.1 200 OK; emitting SSE usage plus headers: "
            + ", ".join(f"{k}={v}" for k, v in emitted_headers.items()),
        )
        self.send_response(200)
        for name, value in emitted_headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(mock_sse_body())
        self.wfile.flush()


class ProxyHandler(BaseHTTPRequestHandler):
    server_version = "HeaderProxyPOC/1.0"
    upstream_url = ""
    mode = "strip"

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/messages":
            self.send_error(404)
            return
        length = int(self.headers.get("content-length", "0") or 0)
        body = self.rfile.read(length)
        req = Request(
            self.upstream_url,
            data=body,
            method="POST",
            headers={
                "content-type": self.headers.get("content-type", "application/json"),
                "anthropic-version": self.headers.get(
                    "anthropic-version", "2023-06-01"
                ),
            },
        )
        with urlopen(req, timeout=10) as resp:
            response_body = resp.read()
            upstream_headers = {k.lower(): v for k, v in resp.headers.items()}
            log_event(
                f"PROXY:{self.mode}",
                f"upstream status HTTP/1.1 {resp.status}; observed headers: "
                + ", ".join(
                    f"{k}={v}"
                    for k, v in sorted(upstream_headers.items())
                    if k in RELEVANT_HEADERS or k == "content-type"
                ),
            )
            self.send_response(resp.status)
            downstream_headers: dict[str, str] = {}
            if self.mode == "forward":
                for name, value in resp.headers.items():
                    lname = name.lower()
                    if lname in HOP_BY_HOP_HEADERS:
                        continue
                    if lname == "content-type" or lname in RELEVANT_HEADERS:
                        self.send_header(name, value)
                        downstream_headers[lname] = value
                self.send_header("x-poc-proxy-mode", "forward")
                downstream_headers["x-poc-proxy-mode"] = "forward"
            else:
                content_type = resp.headers.get("content-type", "")
                self.send_header("content-type", content_type)
                self.send_header("cache-control", "no-cache")
                self.send_header("connection", "close")
                self.send_header("x-poc-proxy-mode", "strip")
                downstream_headers = {
                    "content-type": content_type,
                    "cache-control": "no-cache",
                    "connection": "close",
                    "x-poc-proxy-mode": "strip",
                }
            log_event(
                f"PROXY:{self.mode}",
                "downstream headers sent to client: "
                + ", ".join(f"{k}={v}" for k, v in sorted(downstream_headers.items())),
            )
            self.end_headers()
            self.wfile.write(response_body)
            self.wfile.flush()


@dataclass
class ProbeResult:
    name: str
    url: str
    status: int
    status_line: str
    relevant_headers: dict[str, str]
    saw_usage_in_body: bool
    usage_events: list[dict]
    body_preview: str


def start_server(handler_cls: type[BaseHTTPRequestHandler], port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def make_proxy_handler(upstream_url: str, mode: str) -> type[ProxyHandler]:
    class ConfiguredProxyHandler(ProxyHandler):
        pass

    ConfiguredProxyHandler.upstream_url = upstream_url
    ConfiguredProxyHandler.mode = mode
    return ConfiguredProxyHandler


def parse_usage_events(body: str) -> list[dict]:
    usage_events: list[dict] = []
    for block in body.split("\n\n"):
        data_lines = [line[5:].strip() for line in block.splitlines() if line.startswith("data:")]
        if not data_lines:
            continue
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            if isinstance(payload.get("usage"), dict):
                usage_events.append(payload["usage"])
            message = payload.get("message")
            if isinstance(message, dict) and isinstance(message.get("usage"), dict):
                usage_events.append(message["usage"])
    return usage_events


def probe(name: str, url: str) -> ProbeResult:
    body = json.dumps(
        {
            "model": "claude-mock-poc",
            "max_tokens": 32,
            "stream": True,
            "messages": [{"role": "user", "content": "hello"}],
        }
    ).encode("utf-8")
    parsed = urlparse(url)
    conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=10)
    conn.request(
        "POST",
        parsed.path,
        body=body,
        headers={
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "authorization": "Bearer mock-oauth-token",
        },
    )
    resp = conn.getresponse()
    raw_body = resp.read().decode("utf-8", errors="replace")
    headers = {k.lower(): v for k, v in resp.getheaders()}
    status_line = f"HTTP/{resp.version // 10}.{resp.version % 10} {resp.status} {resp.reason}"
    relevant = {
        key: headers[key]
        for key in sorted(headers)
        if key in RELEVANT_HEADERS or key == "content-type" or key == "x-poc-proxy-mode"
    }
    usage_events = parse_usage_events(raw_body)
    log_event(
        f"CLIENT:{name}",
        f"{status_line}; observed headers: "
        + ", ".join(f"{k}={v}" for k, v in relevant.items())
        + f"; usage_events={len(usage_events)}",
    )
    conn.close()
    return ProbeResult(
        name=name,
        url=url,
        status=resp.status,
        status_line=status_line,
        relevant_headers=relevant,
        saw_usage_in_body=bool(usage_events),
        usage_events=usage_events,
        body_preview=raw_body[:300],
    )


def print_table(results: Iterable[ProbeResult]) -> None:
    print()
    print("POC result")
    print("----------")
    print(f"{'path':<9} {'status':<6} {'usage_body':<11} {'quota_headers':<13} headers")
    for result in results:
        quota_count = sum(
            1 for key in result.relevant_headers if key.startswith("anthropic-ratelimit-")
        )
        print(
            f"{result.name:<9} {result.status:<6} {str(result.saw_usage_in_body):<11} "
            f"{quota_count:<13} {', '.join(result.relevant_headers.keys())}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evidence",
        default=str(Path(__file__).resolve().parent / "evidence" / "latest-run.json"),
        help="Path to write JSON evidence.",
    )
    parser.add_argument(
        "--log",
        default=str(Path(__file__).resolve().parent / "evidence" / "latest-run.log"),
        help="Path to write human-readable evidence log.",
    )
    args = parser.parse_args()

    upstream_port = free_port()
    strip_port = free_port()
    forward_port = free_port()

    upstream_url = f"http://127.0.0.1:{upstream_port}/v1/messages"
    upstream = start_server(MockAnthropicHandler, upstream_port)
    strip_proxy = start_server(make_proxy_handler(upstream_url, "strip"), strip_port)
    forward_proxy = start_server(make_proxy_handler(upstream_url, "forward"), forward_port)
    log_event(
        "POC",
        f"started mock upstream={upstream_url}; strip=http://127.0.0.1:{strip_port}/v1/messages; "
        f"forward=http://127.0.0.1:{forward_port}/v1/messages",
    )
    time.sleep(0.05)

    try:
        results = [
            probe("direct", upstream_url),
            probe("strip", f"http://127.0.0.1:{strip_port}/v1/messages"),
            probe("forward", f"http://127.0.0.1:{forward_port}/v1/messages"),
        ]
        print_table(results)

        evidence = {
            "purpose": "Demonstrate that proxy header stripping can hide client-visible quota signals while preserving SSE usage events.",
            "created_at_unix": time.time(),
            "relevant_headers": RELEVANT_HEADERS,
            "results": [asdict(result) for result in results],
            "event_log": list(EVENT_LOG),
            "assertions": {},
        }

        by_name = {result.name: result for result in results}
        evidence["assertions"] = {
            "direct_has_quota_headers": any(
                key.startswith("anthropic-ratelimit-")
                for key in by_name["direct"].relevant_headers
            ),
            "strip_preserves_usage_body": by_name["strip"].saw_usage_in_body,
            "strip_drops_quota_headers": not any(
                key.startswith("anthropic-ratelimit-")
                for key in by_name["strip"].relevant_headers
            ),
            "forward_preserves_usage_body": by_name["forward"].saw_usage_in_body,
            "forward_preserves_quota_headers": any(
                key.startswith("anthropic-ratelimit-")
                for key in by_name["forward"].relevant_headers
            ),
        }

        evidence_path = Path(args.evidence)
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        log_path = Path(args.log)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("\n".join(EVENT_LOG) + "\n", encoding="utf-8")
        print()
        print(f"Evidence written: {evidence_path}")
        print(f"Evidence log written: {log_path}")

        failed = [name for name, ok in evidence["assertions"].items() if not ok]
        if failed:
            print(f"FAIL: {', '.join(failed)}")
            return 1
        print("PASS: header-loss hypothesis reproduced locally.")
        return 0
    finally:
        forward_proxy.shutdown()
        strip_proxy.shutdown()
        upstream.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
