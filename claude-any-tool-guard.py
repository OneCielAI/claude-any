#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import hashlib
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
REQUIRED_KEYS = {
    "Bash": {"command"},
    "Read": {"file_path"},
    "Write": {"file_path", "content"},
    "Edit": {"file_path", "old_string", "new_string"},
    "MultiEdit": {"file_path", "edits"},
    "Glob": {"pattern"},
    "Grep": {"pattern"},
    "TaskUpdate": {"taskId", "status"},
}
TOOL_HINTS = {
    "Bash": "Use Bash with command, description, timeout, and run_in_background only.",
    "Read": "Use Read with file_path, offset, and limit only.",
    "Write": "Use Write with file_path and content only.",
    "Edit": "Use Edit with file_path, old_string, new_string, and replace_all only.",
    "MultiEdit": "Use MultiEdit with file_path and edits only.",
    "Glob": "Use Glob with pattern and optional path only.",
    "Grep": "Use Grep with pattern, path, glob, type, output_mode, context, head_limit, or multiline only.",
    "TaskUpdate": "Use TaskUpdate with taskId and status.",
}
PLAN_GUARD_MARKER = "[claude-any-plan-guard]"


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


def log_json_event(event: dict[str, Any], result: dict[str, Any] | None = None) -> None:
    try:
        path = cache_dir() / "tool-events.jsonl"
        if path.exists() and path.stat().st_size > 2_000_000:
            path.replace(path.with_suffix(".jsonl.1"))
        record = {
            "time": int(time.time()),
            "hook_event_name": event.get("hook_event_name"),
            "tool_name": event.get("tool_name"),
            "tool_input": event.get("tool_input"),
        }
        if result is not None:
            record["guard_result"] = result
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
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
    log_json_event({"hook_event_name": "PreToolUse", "tool_input": updated}, out)
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
    log_json_event({"hook_event_name": "PreToolUse"}, out)
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


def task_dir(session_id: str) -> Path:
    return Path.home() / ".claude" / "tasks" / session_id


def has_in_progress_task(session_id: str | None) -> bool:
    if not session_id:
        return False
    path = task_dir(session_id)
    if not path.exists():
        return False
    for item in path.glob("*.json"):
        try:
            data = json.loads(item.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        if isinstance(data, dict) and data.get("status") == "in_progress":
            return True
    return False


def transcript_latest_user_text(transcript_path: str | None) -> str:
    if not transcript_path:
        return ""
    path = Path(transcript_path)
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-80:]
    except Exception:
        return ""
    for line in reversed(lines):
        try:
            data = json.loads(line)
        except Exception:
            continue
        if data.get("type") != "user":
            continue
        message = data.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
            return "\n".join(part for part in parts if part).strip()
    return ""


def transcript_plan_mode_active(transcript_path: str | None) -> bool:
    if not transcript_path:
        return False
    path = Path(transcript_path)
    if not path.exists():
        return False
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-240:]
    except Exception:
        return False
    active = False
    tool_names_by_id: dict[str, str] = {}
    for line in lines:
        try:
            data = json.loads(line)
        except Exception:
            continue
        attachment = data.get("attachment")
        if isinstance(attachment, dict):
            attachment_type = attachment.get("type")
            if attachment_type in {"plan_mode", "plan_mode_reentry"}:
                active = True
            elif attachment_type == "plan_mode_exit":
                active = False
        message = data.get("message")
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        blocks = content if isinstance(content, list) else []
        if role == "assistant":
            for block in blocks:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tool_id = str(block.get("id") or "")
                name = str(block.get("name") or "")
                if tool_id and name:
                    tool_names_by_id[tool_id] = name
        elif role == "user":
            for block in blocks:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                tool_use_id = str(block.get("tool_use_id") or "")
                tool_name = tool_names_by_id.get(tool_use_id)
                if tool_name == "EnterPlanMode":
                    active = True
                elif tool_name == "ExitPlanMode":
                    active = False
    return active


def message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "\n".join(part for part in parts if part).strip()


def message_has_tool_use(message: dict[str, Any]) -> bool:
    content = message.get("content")
    if not isinstance(content, list):
        return False
    return any(isinstance(block, dict) and block.get("type") == "tool_use" for block in content)


def transcript_latest_turn(transcript_path: str | None) -> dict[str, Any]:
    if not transcript_path:
        return {}
    path = Path(transcript_path)
    if not path.exists():
        return {}
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-160:]
    except Exception:
        return {}

    latest_assistant: dict[str, Any] | None = None
    latest_assistant_index = -1
    parsed: list[dict[str, Any]] = []
    for line in lines:
        try:
            data = json.loads(line)
        except Exception:
            continue
        parsed.append(data)
        message = data.get("message")
        if isinstance(message, dict) and message.get("role") == "assistant":
            latest_assistant = message
            latest_assistant_index = len(parsed) - 1

    if not latest_assistant:
        return {}

    latest_user_text = ""
    for data in reversed(parsed[:latest_assistant_index]):
        if data.get("type") != "user":
            continue
        message = data.get("message")
        if not isinstance(message, dict):
            continue
        if message.get("isMeta") is True:
            continue
        text = message_text(message)
        if not text:
            continue
        if text.startswith("Stop hook feedback:") or PLAN_GUARD_MARKER in text:
            continue
        if text.startswith("Claude Any plan guard:"):
            continue
        latest_user_text = text
        break

    return {
        "assistant_text": message_text(latest_assistant),
        "assistant_has_tool_use": message_has_tool_use(latest_assistant),
        "user_text": latest_user_text,
    }


def short_resume_prompt(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized or len(normalized) > 32:
        return False
    return not re.search(r"[?？`{};/\\\\]|https?://", normalized)


def non_actionable_stop_text(text: str) -> bool:
    stripped = (text or "").strip()
    normalized = re.sub(r"\s+", " ", stripped).strip()
    if not normalized or len(normalized) > 220:
        return False
    if "\n" in stripped:
        return False
    if re.search(r"[`{};/\\\\]|https?://", normalized):
        return False
    return True


def should_block_plan_stop(transcript_path: str | None) -> tuple[bool, str]:
    if not transcript_plan_mode_active(transcript_path):
        return False, ""
    turn = transcript_latest_turn(transcript_path)
    assistant_text = str(turn.get("assistant_text") or "")
    user_text = str(turn.get("user_text") or "")
    if turn.get("assistant_has_tool_use"):
        return False, ""
    if not non_actionable_stop_text(assistant_text):
        return False, ""
    if re.search(r"[?？]", assistant_text):
        return False, ""
    if not short_resume_prompt(user_text):
        return False, ""
    reason = (
        f"{PLAN_GUARD_MARKER} Claude Any plan guard: Claude Code is still in plan mode, "
        "but the latest response ended as a short "
        "acknowledgement without any concrete tool call. Continue now by calling the next required Claude Code "
        "plan-mode-safe tool, such as Read, Glob, Grep, or ExitPlanMode. Use TaskUpdate only when an existing "
        "task is being updated. If mutation is required, call ExitPlanMode with the plan first. Do not put the "
        "next step into the user input box and do not wait for the user unless you are asking a real "
        "clarification question."
    )
    return True, reason


def stop_block_count_path(session_id: str) -> Path:
    return cache_dir() / f"stop-block-{session_id or 'unknown'}.json"


def increment_stop_block_count(session_id: str | None, text: str) -> int:
    path = stop_block_count_path(session_id or "unknown")
    key = hashlib.sha256(text.strip().encode("utf-8", errors="ignore")).hexdigest()[:16]
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    count = int(data.get(key) or 0) + 1
    data[key] = count
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return count


def reset_stop_block_count(session_id: str | None) -> None:
    if not session_id:
        return
    path = stop_block_count_path(session_id)
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def handle_stop(event: dict[str, Any]) -> int:
    log_json_event(event)
    if str(event.get("hook_event_name") or "") == "SubagentStop":
        log_event(f"SubagentStop guard observed session={event.get('session_id') or ''}")
        return 0
    session_id = str(event.get("session_id") or "")
    transcript_path = str(event.get("transcript_path") or "")
    if active():
        should_block, reason = should_block_plan_stop(transcript_path)
        if should_block:
            count = increment_stop_block_count(session_id, reason)
            if count <= 3:
                out = {"decision": "block", "reason": reason, "suppressOutput": True}
                log_json_event(event, out)
                log_event(f"Stop guard blocked plan idle session={session_id} count={count} transcript={transcript_path}")
                emit(out)
                return 0
            log_event(f"Stop guard allowed repeated plan idle session={session_id} count={count} transcript={transcript_path}")
    log_event(f"Stop guard observed session={session_id}")
    return 0


def normalize_aliases(tool: str, tool_input: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    updated = dict(tool_input)
    changed: list[str] = []

    def alias(target: str, *names: str) -> None:
        if target in updated:
            return
        for name in names:
            value = updated.get(name)
            if value not in (None, ""):
                updated[target] = value
                changed.append(f"{name}->{target}")
                return

    if tool == "Bash":
        alias("command", "cmd", "content", "script")
    elif tool in {"Read", "Write", "Edit", "MultiEdit"}:
        alias("file_path", "path", "file", "filename")
    elif tool == "Glob":
        alias("pattern", "glob", "path_pattern")
    elif tool == "Grep":
        alias("pattern", "query", "search", "regex")
    elif tool == "LS":
        alias("path", "file_path", "directory")
    elif tool == "TaskUpdate":
        alias("taskId", "task_id", "id")
    return updated, changed


def missing_required_keys(tool: str, tool_input: dict[str, Any]) -> list[str]:
    required = REQUIRED_KEYS.get(tool, set())
    missing: list[str] = []
    for key in sorted(required):
        value = tool_input.get(key)
        if value is None or value == "":
            missing.append(key)
    return missing


def strip_unknown_keys(tool: str, tool_input: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    tool_input, changed = normalize_aliases(tool, tool_input)
    allowed = STRICT_KEYS.get(tool)
    if not allowed:
        updated = dict(tool_input)
        dropped: list[str] = []
        if tool in DROP_DESCRIPTION and "description" in updated:
            updated.pop("description", None)
            dropped.append("description")
        return updated, dropped, changed
    updated = {k: v for k, v in tool_input.items() if k in allowed}
    dropped = [k for k in tool_input if k not in allowed]
    return updated, dropped, changed


def handle_pre_tool(event: dict[str, Any]) -> None:
    tool = str(event.get("tool_name") or "")
    if tool.startswith("mcp__"):
        return
    log_json_event(event)
    reset_stop_block_count(str(event.get("session_id") or ""))
    raw = event.get("tool_input")
    if not isinstance(raw, dict):
        pre_deny(
            f"{tool} tool input must be a JSON object.",
            "Regenerate the tool call with a valid JSON object matching the Claude Code tool schema.",
        )
        return

    if tool in {"EnterPlanMode", "ExitPlanMode"}:
        transcript_path = str(event.get("transcript_path") or "")
        if transcript_path:
            in_plan_mode = transcript_plan_mode_active(transcript_path)
            if tool == "EnterPlanMode" and in_plan_mode:
                log_event(f"PreToolUse denied repeated EnterPlanMode transcript={transcript_path}")
                pre_deny(
                    "Claude Code is already in plan mode.",
                    "Continue the current plan-mode exploration. Do not call EnterPlanMode again.",
                )
                return
            if tool == "ExitPlanMode" and not in_plan_mode:
                log_event(f"PreToolUse denied stale ExitPlanMode transcript={transcript_path}")
                pre_deny(
                    "Claude Code is not currently in plan mode.",
                    "If the plan was already approved or plan mode was exited, continue with concrete work instead of calling ExitPlanMode. If planning is required again, enter plan mode first.",
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

    updated, dropped, changed = strip_unknown_keys(tool, raw)
    missing = missing_required_keys(tool, updated)
    if missing:
        log_event(f"PreToolUse denied tool={tool} missing={missing} keys={list(raw.keys())}")
        pre_deny(
            f"{tool} tool input is missing required parameter(s): {', '.join(missing)}.",
            TOOL_HINTS.get(tool, "Regenerate the tool call with the documented Claude Code tool schema."),
        )
        return
    if dropped or changed:
        reason_parts = []
        if dropped:
            reason_parts.append(f"removed unsupported parameter(s): {', '.join(dropped)}")
        if changed:
            reason_parts.append(f"normalized parameter name(s): {', '.join(changed)}")
        reason = "; ".join(reason_parts)
        log_event(f"PreToolUse sanitized tool={tool} dropped={dropped} changed={changed} keys={list(raw.keys())}")
        pre_allow(
            updated,
            f"Claude Any {reason} for {tool}.",
            f"{tool} was generated with non-standard parameter(s). The guard normalized the input before execution.",
        )


def handle_post_failure(event: dict[str, Any]) -> None:
    log_json_event(event)
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


OBSERVE_ONLY_EVENTS = {
    "PostToolUse",
    "PostToolBatch",
    "PermissionRequest",
    "PermissionDenied",
    "SessionStart",
    "SessionEnd",
    "Setup",
    "UserPromptSubmit",
    "UserPromptExpansion",
    "StopFailure",
    "InstructionsLoaded",
    "ConfigChange",
    "CwdChanged",
    "Notification",
    "SubagentStart",
    "TeammateIdle",
    "PreCompact",
    "PostCompact",
    "Elicitation",
    "ElicitationResult",
}


def handle_worktree_create(event: dict[str, Any]) -> int:
    """
    Emit a worktreePath for Claude Code's Agent isolation. In non-git
    directories, Claude Code errors with 'Cannot create agent worktree: not in a
    git repository and no WorktreeCreate hooks are configured'. Returning the
    base_path as worktreePath lets the subagent proceed in the same directory
    (no real isolation, but execution is not blocked).
    """
    base_path = ""
    for key in ("base_path", "cwd", "worktree_path"):
        candidate = event.get(key)
        if isinstance(candidate, str) and candidate.strip():
            base_path = candidate.strip()
            break
    if not base_path:
        log_event("WorktreeCreate received without base_path; emitting empty path")
        emit({
            "hookSpecificOutput": {
                "hookEventName": "WorktreeCreate",
                "worktreePath": "",
            }
        })
        return 0
    log_event(f"WorktreeCreate stub worktreePath={base_path}")
    emit({
        "hookSpecificOutput": {
            "hookEventName": "WorktreeCreate",
            "worktreePath": base_path,
        }
    })
    return 0


def handle_worktree_remove(event: dict[str, Any]) -> int:
    path = str(event.get("worktree_path") or "").strip()
    if path:
        log_event(f"WorktreeRemove noop path={path}")
    return 0


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    name = str(event.get("hook_event_name") or "")

    # Worktree handlers always run, regardless of provider, so the non-git
    # worktree fallback works whenever the hook is installed at all.
    if name == "WorktreeCreate":
        return handle_worktree_create(event)
    if name == "WorktreeRemove":
        return handle_worktree_remove(event)
    if name in {"Stop", "SubagentStop"}:
        return handle_stop(event)

    # Lightweight observation for events we do not act on. Skip when inactive
    # to avoid touching disk on every event.
    if name in OBSERVE_ONLY_EVENTS:
        if active():
            try:
                log_json_event(event)
            except Exception:
                pass
        return 0

    # Tool/task events: keep existing provider gating.
    provider = os.environ.get("CLAUDE_ANY_PROVIDER", "").strip()
    if not active():
        if provider:
            log_event(f"inactive provider={provider}")
        return 0
    if name == "PreToolUse":
        tool = str(event.get("tool_name") or "")
        raw = event.get("tool_input")
        keys = list(raw.keys()) if isinstance(raw, dict) else []
        log_event(f"PreToolUse seen provider={provider} tool={tool} keys={keys}")
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
