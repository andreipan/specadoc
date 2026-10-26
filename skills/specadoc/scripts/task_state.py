"""Small, durable task state stored in the existing baseline file, not an event tree."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from validate_change import (Document, PENDING, TASK_CHECKBOX, evidence_is_current, files_field_hash, ids_in,
                             task_fields)

SCHEMA = "specadoc.task/v2"


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def task_block(plan: Document, task: str) -> tuple[int, int, dict[str, str]]:
    for identifier, start, end in plan.blocks("Tasks", "T"):
        if identifier == task:
            return start, end, task_fields(plan, start, end)
    raise ValueError(f"plan.md has no task {task}")


def approval_error(plan: Document) -> str | None:
    body = "\n".join(line for _, line in plan.body("Plan approval"))
    status = re.search(r"\*\*Status:\*\*\s*([^\n]+)", body)
    if not status or not re.match(r"(?:approved|accepted|одобрен|утвержд)", status[1].strip(), re.I):
        return "plan approval is required before apply or dispatch"
    if re.search(r"\b(?:not|unapproved|awaiting|pending|TBD)\b", status[1], re.I):
        return "plan approval is not complete"
    return None


def readiness(plan: Document, task: str) -> list[str]:
    errors = []
    if error := approval_error(plan):
        errors.append(error)
    _, _, fields = task_block(plan, task)
    if fields.get("Owner", "").lower() != "worker":
        errors.append(f"{task}: dispatch requires Owner: worker")
    if fields.get("Decision risk", "").lower() != "low":
        errors.append(f"{task}: resolve material decisions before worker dispatch")
    open_decisions = fields.get("Open decisions", "None").strip()
    if open_decisions.lower() not in ("none", "n/a", "нет", "-"):
        errors.append(f"{task}: unresolved decisions: {open_decisions}")
    blocks = {identifier: (start, end) for identifier, start, end in plan.blocks("Tasks", "T")}

    def visit(current: str, trail: tuple[str, ...]) -> None:
        if current in trail:
            errors.append("task dependency cycle: " + " -> ".join((*trail, current)))
            return
        if current not in blocks:
            errors.append(f"{task}: missing dependency {current}")
            return
        start, end = blocks[current]
        for dependency in ids_in(task_fields(plan, start, end).get("Depends on", ""), "T"):
            if dependency in blocks:
                a, b = blocks[dependency]
                marks = [m["mark"] for line in plan.lines[a:b] if (m := TASK_CHECKBOX.match(line))]
                if not marks or any(mark == " " for mark in marks):
                    errors.append(f"{task}: dependency {dependency} is not complete")
                state_path = plan.path.parent / "runs" / f"{dependency}-baseline.json"
                if state_path.is_file():
                    try:
                        state = json.loads(state_path.read_text(encoding="utf-8"))
                        if state.get("schema") == SCHEMA:
                            if state.get("state") != "accepted":
                                errors.append(f"{task}: dependency {dependency} has not been accepted")
                            else:
                                files = task_fields(plan, a, b).get("Files", "")
                                fresh = evidence_is_current(state_path.parent, dependency, files)
                                if fresh is None:
                                    recorded = state.get("verification", {}).get("files_hash")
                                    fresh = bool(recorded) and files_field_hash(files) == recorded
                                if not fresh:
                                    errors.append(f"{task}: dependency {dependency} accepted evidence is stale; "
                                                  "re-verify it, or reopen it for the drifted files")
                    except (OSError, ValueError, TypeError, AttributeError):
                        errors.append(f"{task}: dependency {dependency} acceptance state is unreadable")
            visit(dependency, (*trail, current))
    visit(task, ())
    return list(dict.fromkeys(errors))


def safe_path(value: str, *, allow_missing: bool = True, allow_absolute: bool = False) -> Path:
    """A literal path inside the repository. Brackets and braces are literal
    (`app/[slug]/page.tsx`); wildcards are not."""
    path = Path(value)
    if (not value or (path.is_absolute() and not allow_absolute) or ".." in path.parts or ".git" in path.parts
            or any(c in value for c in "*?\\`\n\r\x00")):
        raise ValueError(f"expected a literal repository-relative path: {value}")
    resolved = path.resolve()
    if not resolved.is_relative_to(Path.cwd().resolve()):
        raise ValueError(f"path leaves repository: {value}")
    if not allow_missing and not resolved.is_file():
        raise ValueError(f"file does not exist: {value}")
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "deleted"


def update_task(plan: Document, task: str, values: dict[str, str], *, complete: bool = False, reopen: bool = False) -> str:
    """Set task fields in place; repeated calls produce identical text."""
    start, end, _ = task_block(plan, task)
    block = plan.lines[start:end]
    while block and not block[-1].strip():
        block.pop()
    for key, value in values.items():
        value = " ".join(value.split())
        prefix = f"- **{key}:**"
        matches = [i for i, line in enumerate(block) if line.startswith(prefix)]
        if matches:
            first = matches[0]
            # Drop indented continuation lines of the old (often template) value.
            last = first + 1
            while last < len(block) and block[last].startswith((" ", "\t")) and block[last].strip():
                last += 1
            block[first:last] = [f"{prefix} {value}"]
        else:
            block.append(f"{prefix} {value}")
    if complete:
        block = [re.sub(r"^- \[ \] Complete\s*$", "- [x] Complete", line) for line in block]
    elif reopen:
        block = [re.sub(r"^- \[[xX]\] Complete\s*$", "- [ ] Complete", line) for line in block]
    rest = plan.lines[end:]
    while rest and not rest[0].strip():
        rest = rest[1:]
    tail = [""] + rest if rest else []
    return "\n".join(plan.lines[:start] + block + tail).rstrip("\n") + "\n"
