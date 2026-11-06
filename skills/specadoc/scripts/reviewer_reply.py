"""Save a native reviewer's final reply from its own transcript (`--from-agent`).

Controllers used to retype the reviewer's reply into a result file (4.1/4.2):
the recorded verdict then had no provenance. This reads the reviewer
subagent's transcript, writes its final reply verbatim under `runs/`, and lets
`review-result` / `design-review` parse that file.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

AGENT_ID = re.compile(r"[0-9A-Za-z_-]{6,80}")


def _home() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))


def find_transcript(agent: str, project: Path | None = None) -> Path:
    """The subagent transcript `<session>/subagents/agent-<id>.jsonl`, this project first."""
    if not AGENT_ID.fullmatch(agent):
        raise ValueError(f"invalid agent id: {agent!r}")
    projects = _home() / "projects"
    name = f"agent-{agent}.jsonl"
    if project is not None:
        directory = projects / re.sub(r"[^A-Za-z0-9]", "-", str(project.resolve()))
        if found := sorted(directory.glob(f"*/subagents/{name}")):
            return found[-1]
    if found := sorted(projects.glob(f"*/*/subagents/{name}")):
        return found[-1]
    raise ValueError(f"no transcript for agent {agent} under {projects}; pass --result-file instead")


def final_reply(transcript: Path) -> str:
    """Text of the last assistant message: its text blocks, else a hand-back tool's message."""
    reply = ""
    with transcript.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") != "assistant":
                continue
            content = (record.get("message") or {}).get("content")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                texts = [item.get("text", "") for item in content
                         if isinstance(item, dict) and item.get("type") == "text"]
                handbacks = [value for item in content
                             if isinstance(item, dict) and item.get("type") == "tool_use"
                             for key in ("message", "result")
                             if isinstance(value := (item.get("input") or {}).get(key), str)]
                text = "\n".join(t for t in texts if t.strip()) or (handbacks[-1] if handbacks else "")
            else:
                text = ""
            if text.strip():
                reply = text
    if not reply.strip():
        raise ValueError(f"agent transcript {transcript} has no final reply")
    return reply


def save_reply(agent: str, target: Path) -> Path:
    """Write the agent's final reply to `target` (under the change's runs/) unchanged."""
    reply = final_reply(find_transcript(agent, Path.cwd()))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(reply.rstrip("\n") + "\n", encoding="utf-8")
    return target


def previous_agent(text: str) -> str | None:
    """The last `Reviewer agent:` recorded in a plan section or round block."""
    found = re.findall(r"\*\*Reviewer agent:\*\*\s*`?([0-9A-Za-z_-]+)`?", text)
    return found[-1] if found else None
