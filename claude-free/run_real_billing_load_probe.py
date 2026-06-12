#!/usr/bin/env python3
"""High-volume billing/usage probe for real Claude Code + claude-any routed mode.

This script is intentionally gated. By default it performs a dry run only.
Real execution may consume substantial Claude/Anthropic quota and must be
enabled explicitly with both:

    --execute-real --i-understand-cost

The recommended proof shape is cumulative rather than one giant prompt:

    50k estimated input tokens x 20 calls ~= 1M input tokens

That avoids single-request context limits while still producing a measurable
usage/quota signal.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CLAUDE_ANY = ROOT / "claude_any.py"
EVIDENCE_ROOT = Path(__file__).resolve().parent / "evidence"


def stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S", time.gmtime())


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


class Timeline:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lines: list[str] = []
        path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, component: str, message: str) -> None:
        line = f"{iso_now()} [{component}] {message}"
        self.lines.append(line)
        self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        print(line)


def estimate_tokens(text: str) -> int:
    # Conservative rough estimator. The evidence should use provider/Claude logs
    # where available; this is only for planning and prompt sizing.
    return max(1, len(text) // 4)


def make_payload_line(rng: random.Random, call_index: int, row: int, anomaly: bool) -> str:
    # Unique synthetic data prevents trivial repeated-text compression behavior
    # in the prompt cache and makes the model inspect the input.
    fields = [
        f"CALL={call_index:03d}",
        f"ROW={row:06d}",
        f"A={rng.getrandbits(48):012x}",
        f"B={rng.getrandbits(48):012x}",
        f"C={rng.getrandbits(48):012x}",
        "ANOMALY=YES" if anomaly else "ANOMALY=no",
        f"TEXT=synthetic-ledger-record-{call_index:03d}-{row:06d}",
    ]
    return " | ".join(fields)


def build_prompt(call_index: int, target_input_tokens: int, seed: int) -> tuple[str, dict[str, Any]]:
    rng = random.Random(seed + call_index)
    lines: list[str] = []
    anomalies: list[int] = []
    target_chars = target_input_tokens * 4
    row = 0
    while sum(len(line) + 1 for line in lines) < target_chars:
        row += 1
        anomaly = row % 997 == 0
        if anomaly:
            anomalies.append(row)
        lines.append(make_payload_line(rng, call_index, row, anomaly))

    payload = "\n".join(lines)
    prompt = f"""You are validating a synthetic billing-load probe.

Read the entire DATA block. Return JSON only with:
- call_index
- line_count
- first_row
- last_row
- anomaly_count
- first_three_anomaly_rows
- final_token: "POC_LOAD_OK"

Do not use tools. Do not explain.

DATA-BEGIN
{payload}
DATA-END
"""
    meta = {
        "call_index": call_index,
        "target_input_tokens": target_input_tokens,
        "estimated_input_tokens": estimate_tokens(prompt),
        "char_count": len(prompt),
        "line_count": len(lines),
        "first_row": 1 if lines else 0,
        "last_row": row,
        "anomaly_count": len(anomalies),
        "first_three_anomaly_rows": anomalies[:3],
        "seed": seed + call_index,
    }
    return prompt, meta


def run_cmd(
    argv: list[str],
    cwd: Path,
    env: dict[str, str],
    timeline: Timeline,
    label: str,
    timeout: float,
    stdin_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    timeline.log(label, "RUN " + " ".join(argv))
    started = time.time()
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        input=stdin_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    timeline.log(
        label,
        f"EXIT rc={proc.returncode} elapsed={time.time() - started:.1f}s stdout_len={len(proc.stdout)} stderr_len={len(proc.stderr)}",
    )
    return proc


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
        try:
            value = json.loads(m.group(2))
        except json.JSONDecodeError:
            value = m.group(2).strip('"')
        result[m.group(1)] = str(value)
    return result


def wait_health(port: int, timeout: float = 20) -> dict[str, Any]:
    import http.client

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
        time.sleep(0.25)
    raise RuntimeError(f"router health not ready: {last_error}")


def terminate(proc: subprocess.Popen[str] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    if os.name == "nt":
        proc.terminate()
    else:
        proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()


@dataclass
class CallResult:
    call_index: int
    prompt_file: str
    estimated_input_tokens: int
    char_count: int
    returncode: int | None
    elapsed_seconds: float | None
    stdout_file: str | None
    stderr_file: str | None
    debug_file: str | None
    stdout_preview: str
    stderr_preview: str


def copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        shutil.copy2(src, dst)
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["routed", "native", "both"], default="routed")
    parser.add_argument("--model", default="claude-sonnet-4-5")
    parser.add_argument("--target-total-tokens", type=int, default=1_000_000)
    parser.add_argument("--tokens-per-call", type=int, default=50_000)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--timeout-per-call", type=float, default=600)
    parser.add_argument("--seed", type=int, default=451045)
    parser.add_argument(
        "--prompts-only",
        action="store_true",
        help="Only generate prompt files/manifests. Do not configure or start claude-any.",
    )
    parser.add_argument("--execute-real", action="store_true")
    parser.add_argument("--i-understand-cost", action="store_true")
    parser.add_argument("--keep-prompts", action="store_true", help="Keep generated prompt files even after real execution.")
    args = parser.parse_args()

    if args.target_total_tokens <= 0 or args.tokens_per_call <= 0:
        raise SystemExit("token counts must be positive")
    call_count = (args.target_total_tokens + args.tokens_per_call - 1) // args.tokens_per_call
    if args.execute_real and not args.i_understand_cost:
        raise SystemExit(
            "Refusing real high-volume execution without --i-understand-cost. "
            "This may consume substantial Claude/Anthropic quota."
        )

    run_dir = EVIDENCE_ROOT / f"real-load-{stamp()}"
    prompts_dir = run_dir / "prompts"
    calls_dir = run_dir / "calls"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    calls_dir.mkdir(parents=True, exist_ok=True)
    timeline = Timeline(run_dir / "timeline.log")

    timeline.log(
        "PLAN",
        f"mode={args.mode} model={args.model} target_total_tokens={args.target_total_tokens} "
        f"tokens_per_call={args.tokens_per_call} calls={call_count} execute_real={args.execute_real} "
        f"prompts_only={args.prompts_only}",
    )

    call_results: list[CallResult] = []
    total_estimated = 0
    prompt_metas: list[dict[str, Any]] = []
    for call_index in range(1, call_count + 1):
        remaining = args.target_total_tokens - total_estimated
        per_call = min(args.tokens_per_call, max(args.tokens_per_call, remaining))
        prompt, meta = build_prompt(call_index, per_call, args.seed)
        prompt_file = prompts_dir / f"call-{call_index:03d}.txt"
        prompt_file.write_text(prompt, encoding="utf-8")
        total_estimated += int(meta["estimated_input_tokens"])
        prompt_metas.append(meta)
        call_results.append(
            CallResult(
                call_index=call_index,
                prompt_file=str(prompt_file),
                estimated_input_tokens=int(meta["estimated_input_tokens"]),
                char_count=int(meta["char_count"]),
                returncode=None,
                elapsed_seconds=None,
                stdout_file=None,
                stderr_file=None,
                debug_file=None,
                stdout_preview="",
                stderr_preview="",
            )
        )
        if total_estimated >= args.target_total_tokens:
            break

    (run_dir / "prompt-manifest.json").write_text(json.dumps(prompt_metas, indent=2), encoding="utf-8")
    timeline.log("PLAN", f"generated_prompts={len(call_results)} estimated_input_tokens={total_estimated}")

    if args.prompts_only:
        summary = {
            "purpose": "Prompt-only preparation for high-volume interactive Claude Code billing/usage evidence.",
            "warning": "No claude-any router was started and no Claude/Anthropic request was made.",
            "mode": args.mode,
            "model": args.model,
            "target_total_tokens": args.target_total_tokens,
            "tokens_per_call": args.tokens_per_call,
            "generated_call_count": len(call_results),
            "estimated_generated_input_tokens": total_estimated,
            "execute_real": False,
            "prompts_only": True,
            "calls": [asdict(r) for r in call_results],
            "manual_billing_check": {
                "before": "Capture /usage before pasting any generated prompt.",
                "after": "Capture /usage after each generated prompt completes.",
            },
        }
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        timeline.log("DRY-RUN", "Prompt-only preparation complete. No router or Claude process was started.")
        print()
        print(f"Evidence directory: {run_dir}")
        return 0

    router_proc: subprocess.Popen[str] | None = None
    config_dir = run_dir / "claude-any-config"
    router_port = free_port()
    base_env = os.environ.copy()
    base_env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(args.max_output_tokens)

    try:
        routed_env: dict[str, str] | None = None
        if args.mode in {"routed", "both"}:
            env = base_env.copy()
            env["CLAUDE_ANY_CONFIG_DIR"] = str(config_dir)
            env["CLAUDE_ANY_ROUTER_PORT"] = str(router_port)
            setup = run_cmd(
                [
                    sys.executable,
                    str(CLAUDE_ANY),
                    "cli",
                    "--ca-provider",
                    "anthropic",
                    "--ca-base-url",
                    "https://api.anthropic.com",
                    "--ca-model",
                    args.model,
                    "--ca-provider-option",
                    "route_through_router=true",
                    "--ca-provider-option",
                    f"max_output_tokens={args.max_output_tokens}",
                    "--ca-log-level",
                    "TRACE",
                    "--ca-no-launch",
                ],
                ROOT,
                env,
                timeline,
                "ROUTED-SETUP",
                timeout=60,
            )
            (run_dir / "routed-setup.stdout.txt").write_text(setup.stdout, encoding="utf-8")
            (run_dir / "routed-setup.stderr.txt").write_text(setup.stderr, encoding="utf-8")
            if setup.returncode != 0:
                raise RuntimeError("routed setup failed")

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
            timeline.log("ROUTED", "health=" + json.dumps(health, ensure_ascii=False, sort_keys=True))
            env_cmd = run_cmd([sys.executable, str(CLAUDE_ANY), "env"], ROOT, env, timeline, "ROUTED-ENV", timeout=30)
            (run_dir / "routed-env.txt").write_text(env_cmd.stdout, encoding="utf-8")
            routed_env = env.copy()
            for key, value in parse_export_env(env_cmd.stdout).items():
                if value is None:
                    routed_env.pop(key, None)
                else:
                    routed_env[key] = value

        if not args.execute_real:
            timeline.log("DRY-RUN", "No real Claude calls were made. Add --execute-real --i-understand-cost to run.")
        else:
            claude = shutil.which("claude")
            if not claude:
                raise RuntimeError("claude executable not found")

            modes_to_run = ["native", "routed"] if args.mode == "both" else [args.mode]
            for mode in modes_to_run:
                if mode == "routed":
                    if routed_env is None:
                        raise RuntimeError("routed env was not initialized")
                    exec_env = routed_env.copy()
                else:
                    exec_env = base_env.copy()
                    exec_env.pop("ANTHROPIC_BASE_URL", None)
                    exec_env["ANTHROPIC_MODEL"] = args.model
                    exec_env["CLAUDE_ANY_PROVIDER"] = "anthropic-native-load-probe"

                for result in call_results:
                    prompt = Path(result.prompt_file).read_text(encoding="utf-8")
                    prefix = calls_dir / f"{mode}-call-{result.call_index:03d}"
                    debug_file = prefix.with_suffix(".debug.log")
                    started = time.time()
                    proc = run_cmd(
                        [
                            claude,
                            "-p",
                            "--debug",
                            "--debug-file",
                            str(debug_file),
                        ],
                        run_dir,
                        exec_env,
                        timeline,
                        f"{mode.upper()}-{result.call_index:03d}",
                        timeout=args.timeout_per_call,
                        stdin_text=prompt,
                    )
                    elapsed = time.time() - started
                    stdout_file = prefix.with_suffix(".stdout.txt")
                    stderr_file = prefix.with_suffix(".stderr.txt")
                    stdout_file.write_text(proc.stdout, encoding="utf-8")
                    stderr_file.write_text(proc.stderr, encoding="utf-8")
                    call_results.append(
                        CallResult(
                            call_index=result.call_index,
                            prompt_file=result.prompt_file,
                            estimated_input_tokens=result.estimated_input_tokens,
                            char_count=result.char_count,
                            returncode=proc.returncode,
                            elapsed_seconds=elapsed,
                            stdout_file=str(stdout_file),
                            stderr_file=str(stderr_file),
                            debug_file=str(debug_file),
                            stdout_preview=proc.stdout[:500],
                            stderr_preview=proc.stderr[:500],
                        )
                    )

        # Preserve router artifacts.
        if config_dir.exists():
            for name in ("router.log", "requests.jsonl", "responses.jsonl", "context-usage.json", "rate-limit-state.json"):
                copy_if_exists(config_dir / name, run_dir / name)

        summary = {
            "purpose": "High-volume real billing/usage load probe for Claude Code and claude-any Anthropic routed mode.",
            "warning": "Real execution may consume Claude/Anthropic quota. Dry-run mode makes no real Claude calls.",
            "mode": args.mode,
            "model": args.model,
            "target_total_tokens": args.target_total_tokens,
            "tokens_per_call": args.tokens_per_call,
            "generated_call_count": len([r for r in call_results if r.returncode is None]),
            "estimated_generated_input_tokens": total_estimated,
            "execute_real": args.execute_real,
            "router_port": router_port if args.mode in {"routed", "both"} else None,
            "config_dir": str(config_dir) if args.mode in {"routed", "both"} else None,
            "calls": [asdict(r) for r in call_results],
            "manual_billing_check": {
                "before": "Capture Anthropic/Claude usage dashboard or OAuth usage before execution.",
                "after": "Capture the same usage source after execution and compare against estimated/generated tokens and router logs.",
            },
        }
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print()
        print(f"Evidence directory: {run_dir}")
        return 0
    finally:
        terminate(router_proc)
        if not args.keep_prompts and args.execute_real:
            # Keep prompt manifest. Remove large prompt bodies only after real
            # execution unless the user asked to retain them.
            for path in prompts_dir.glob("call-*.txt"):
                try:
                    path.unlink()
                except OSError:
                    pass


if __name__ == "__main__":
    raise SystemExit(main())
