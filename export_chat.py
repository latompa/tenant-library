#!/usr/bin/env python3
"""Export Claude Code chat history for a project to a markdown file."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_sessions(project_dir: Path) -> list[tuple[str, list[dict]]]:
    """Load all .jsonl session files from a project directory."""
    sessions = []
    for f in sorted(project_dir.glob("*.jsonl")):
        lines = []
        for line in f.read_text().splitlines():
            if line.strip():
                lines.append(json.loads(line))
        if lines:
            sessions.append((f.stem, lines))
    return sessions


def format_timestamp(ts: str) -> str:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def extract_text(content) -> str:
    """Extract readable text from message content."""
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(block["text"])
            elif block.get("type") == "tool_use":
                name = block.get("name", "unknown")
                inp = block.get("input", {})
                if name == "Bash":
                    cmd = inp.get("command", "")
                    parts.append(f"**Tool: Bash**\n```bash\n{cmd}\n```")
                elif name in ("Read", "Write", "Edit"):
                    fp = inp.get("file_path", "")
                    parts.append(f"**Tool: {name}** `{fp}`")
                    if name == "Write" and "content" in inp:
                        parts.append(f"```\n{inp['content']}\n```")
                    elif name == "Edit":
                        old = inp.get("old_string", "")
                        new = inp.get("new_string", "")
                        parts.append(f"```diff\n- {old}\n+ {new}\n```")
                elif name in ("Glob", "Grep"):
                    pattern = inp.get("pattern", "")
                    parts.append(f"**Tool: {name}** `{pattern}`")
                else:
                    parts.append(f"**Tool: {name}**")
            elif block.get("type") == "tool_result":
                result_content = block.get("content", "")
                if isinstance(result_content, str) and result_content.strip():
                    truncated = result_content[:2000]
                    if len(result_content) > 2000:
                        truncated += "\n... (truncated)"
                    parts.append(f"<details><summary>Tool output</summary>\n\n```\n{truncated}\n```\n</details>")
    return "\n\n".join(parts)


def export_session(session_id: str, entries: list[dict]) -> str:
    """Convert a session's entries to markdown."""
    lines = []
    lines.append(f"# Chat Session `{session_id}`\n")

    # Get session metadata from first real message
    for entry in entries:
        if entry.get("type") in ("user", "assistant"):
            version = entry.get("version", "unknown")
            cwd = entry.get("cwd", "unknown")
            lines.append(f"- **Claude Code version:** {version}")
            lines.append(f"- **Working directory:** {cwd}")
            ts = entry.get("timestamp", "")
            if ts:
                lines.append(f"- **Started:** {format_timestamp(ts)}")
            lines.append("")
            break

    lines.append("---\n")

    seen_uuids = set()
    for entry in entries:
        uuid = entry.get("uuid")
        if uuid and uuid in seen_uuids:
            continue
        if uuid:
            seen_uuids.add(uuid)

        entry_type = entry.get("type")
        if entry_type not in ("user", "assistant"):
            continue

        msg = entry.get("message", {})
        role = msg.get("role", entry_type)
        ts = entry.get("timestamp", "")
        content = msg.get("content", "")

        text = extract_text(content)
        if not text.strip():
            continue

        ts_str = format_timestamp(ts) if ts else ""
        role_label = "Human" if role == "user" else "Assistant"

        lines.append(f"### {role_label}")
        lines.append(f"*{ts_str}*\n")
        lines.append(text)
        lines.append("\n---\n")

    return "\n".join(lines)


def main():
    claude_dir = Path.home() / ".claude" / "projects"
    project_name = "-Users-tom-tmp-tenant-library"

    # Allow overriding project via CLI arg
    if len(sys.argv) > 1:
        project_name = sys.argv[1]

    project_dir = claude_dir / project_name
    if not project_dir.exists():
        print(f"Error: project directory not found: {project_dir}")
        sys.exit(1)

    sessions = load_sessions(project_dir)
    if not sessions:
        print("No chat sessions found.")
        sys.exit(1)

    parts = []
    for session_id, entries in sessions:
        parts.append(export_session(session_id, entries))

    output = "\n\n".join(parts)

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = Path(f"chat_export_{now}.md")
    out_file.write_text(output)
    print(f"Exported {len(sessions)} session(s) to {out_file}")


if __name__ == "__main__":
    main()
