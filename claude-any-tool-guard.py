#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any


NON_NATIVE_PROVIDERS = {"ollama", "ollama-cloud", "vllm", "nvidia-hosted", "self-hosted-nim"}
TASK_STATUS = {"pending", "in_progress", "completed", "deleted"}
DESCRIPTION_OK = {"Bash", "TaskCreate", "TaskUpdate"}
DROP_DESCRIPTION = {"Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "LS"}
BASH_KEYS = {"command", "description", "timeout", "run_in_background"}
READ_KEYS = {"file_path", "offset", "limit"}
WRITE_KEYS = {"file_path", "content"}
EDIT_KEYS = {"file_path", "old_string", "new_string", "replace_all"}
MULTIEDIT_KEYS = {"file_path", "edits"}
GLOB_KEYS = {"pattern", "path"}
GREP_KEYS = {"pattern", "path", "glob", "type", "output_mode", "-A", "-B", "-C", "head_limit", "multiline"}
LS_KEYS = {"path", "ignore"}
TASKLIST_KEYS: set[str] = set()
TASKUPDATE_KEYS = {"taskId", "status"}
STRICT_KEYS = {
    "Bash": BASH_KEYS,
    "Read": READ_KEYS,
    "Write": WRITE_KEYS,
    "Edit": EDIT_KEYS,
    "MultiEdit": MULTIEDIT_KEYS,
    "Glob": GLOB_KEYS,
    "Grep": GREP_KEYS,
    "LS": LS_KEYS,
    "TaskList": TASKLIST_KEYS,
    "TaskUpdate": TASKUPDATE_KEYS,
}


def active() -> bool:
    provider = os.environ.get("CLAUDE_ANY_PROVIDER", "").strip()
    return provider in NON_NATIVE_PROVIDERS


def emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


def log_event(message: str) -> None:
    try:
        path = cache_dir() / "events.log"
        if path.exists() and path.stat().st_size > 300_000:
            path.replace(path.with_suffix(".log.1"))
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{int(time.time())} {message}\n")
    except Exception:
        pass


def pre_allow(updated: dict[str, Any], reason: str, context: str = "") -> None:
    out: dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": reason,
            "updatedInput": updated,
        }
    }
    if context:
        out["hookSpecificOutput"]["additionalContext"] = context
    emit(out)


def pre_deny(reason: str, context: str = "") -> None:
    out: dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    if context:
        out["hookSpecificOutput"]["additionalContext"] = context
    emit(out)


def post_failure_context(message: str) -> None:
    emit({"hookSpecificOutput": {"hookEventName": "PostToolUseFailure", "additionalContext": message}})


def cache_dir() -> Path:
    path = Path.home() / ".claude" / "claude-any-tool-guard"
    path.mkdir(parents=True, exist_ok=True)
    return path


def task_cache_path() -> Path:
    return cache_dir() / "tasks.json"


def load_tasks() -> dict[str, Any]:
    path = task_cache_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(errors="ignore"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_tasks(data: dict[str, Any]) -> None:
    path = task_cache_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def known_tasks(session_id: str | None) -> dict[str, Any]:
    data = load_tasks()
    if not session_id:
        return {}
    session = data.get(session_id)
    return session if isinstance(session, dict) else {}


def record_task_created(event: dict[str, Any]) -> None:
    session_id = str(event.get("session_id") or "")
    task_id = str(event.get("task_id") or "")
    if not session_id or not task_id:
        return
    data = load_tasks()
    session = data.setdefault(session_id, {})
    session[task_id] = {
        "subject": event.get("task_subject"),
        "description": event.get("task_description"),
        "created_at": int(time.time()),
    }
    save_tasks(data)


def record_task_completed(event: dict[str, Any]) -> None:
    session_id = str(event.get("session_id") or "")
    task_id = str(event.get("task_id") or "")
    if not session_id or not task_id:
        return
    data = load_tasks()
    session = data.setdefault(session_id, {})
    info = session.setdefault(task_id, {})
    if isinstance(info, dict):
        info["completed_at"] = int(time.time())
        info["status"] = "completed"
    save_tasks(data)


def strip_unknown_keys(tool: str, tool_input: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    if tool == "Bash" and "content" in tool_input and "command" not in tool_input:
        tool_input = dict(tool_input)
        tool_input["command"] = tool_input["content"]
    allowed = STRICT_KEYS.get(tool)
    if not allowed:
        updated = dict(tool_input)
        dropped: list[str] = []
        if tool in DROP_DESCRIPTION and "description" in updated:
            updated.pop("description", None)
            dropped.append("description")
        return updated, dropped
    updated = {k: v for k, v in tool_input.items() if k in allowed}
    dropped = [k for k in tool_input if k not in allowed]
    return updated, dropped


def handle_pre_tool(event: dict[str, Any]) -> None:
    tool = str(event.get("tool_name") or "")
    if tool.startswith("mcp__"):
        return
    raw = event.get("tool_input")
    if not isinstance(raw, dict):
        pre_deny(
            f"{tool} tool input must be a JSON object.",
            "Regenerate the tool call with a valid JSON object matching the Claude Code tool schema.",
        )
        return

    if tool == "TaskUpdate":
        task_id = raw.get("taskId")
        status = raw.get("status")
        if not isinstance(task_id, str) or not task_id.strip():
            tasks = known_tasks(str(event.get("session_id") or ""))
            known = ", ".join(f"{tid} ({info.get('subject')})" for tid, info in sorted(tasks.items())[:8] if isinstance(info, dict))
            context = "TaskUpdate requires a string taskId. Regenerate the call with the exact taskId from the task you intend to update."
            if known:
                context += f" Known task ids for this session: {known}."
            pre_deny("TaskUpdate requires parameter taskId.", context)
            return
        if not isinstance(status, str) or status not in TASK_STATUS:
            pre_deny(
                "TaskUpdate status must be one of pending, in_progress, completed, or deleted.",
                "Regenerate TaskUpdate with a valid status enum and preserve the taskId.",
            )
            return

    updated, dropped = strip_unknown_keys(tool, raw)
    if dropped:
        log_event(f"PreToolUse sanitized tool={tool} dropped={dropped} keys={list(raw.keys())}")
        pre_allow(
            updated,
            f"Removed unsupported parameter(s) for {tool}: {', '.join(dropped)}.",
            f"{tool} was generated with unsupported parameter(s): {', '.join(dropped)}. The guard removed them before execution.",
        )


def handle_post_failure(event: dict[str, Any]) -> None:
    tool = str(event.get("tool_name") or "")
    error = str(event.get("error") or "")
    raw = event.get("tool_input")
    hint = ""
    if "Unrecognized key" in error or "unexpected parameter" in error or "unrecognized_keys" in error:
        hint = (
            f"The {tool} tool rejected unsupported parameters. Retry using only the documented Claude Code schema. "
            "Do not add descriptive fields unless the tool explicitly supports them."
        )
    elif "taskId" in error and tool == "TaskUpdate":
        hint = "TaskUpdate failed because taskId was missing or invalid. Retry with the exact taskId from the task being updated."
    elif "status" in error and tool == "TaskUpdate":
        hint = "TaskUpdate status must be one of pending, in_progress, completed, or deleted."
    if hint:
        log_event(f"PostToolUseFailure tool={tool} error={error[:240]}")
        if isinstance(raw, dict):
            hint += f" Previous invalid input was: {json.dumps(raw, ensure_ascii=False)[:1000]}"
        post_failure_context(hint)


def main() -> int:
    provider = os.environ.get("CLAUDE_ANY_PROVIDER", "").strip()
    if not active():
        if provider:
            log_event(f"inactive provider={provider}")
        return 0
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    name = str(event.get("hook_event_name") or "")
    if name == "PreToolUse":
        tool = str(event.get("tool_name") or "")
        raw = event.get("tool_input")
        keys = list(raw.keys()) if isinstance(raw, dict) else []
        log_event(f"PreToolUse seen provider={provider} tool={tool} keys={keys}")
    if name == "PreToolUse":
        handle_pre_tool(event)
    elif name == "PostToolUseFailure":
        handle_post_failure(event)
    elif name == "TaskCreated":
        record_task_created(event)
    elif name == "TaskCompleted":
        record_task_completed(event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
