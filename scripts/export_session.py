"""Export a Claude Code session (.jsonl) to readable Markdown.

Usage:
    python scripts/export_session.py <session-id>
    python scripts/export_session.py --list

Examples:
    python scripts/export_session.py 2dcda6f2-9b51-45fb-894e-866931da26e7
    python scripts/export_session.py --list          # list available sessions
    python scripts/export_session.py --list --full   # list with first user message

Output is written to data/session-<short-id>.md
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Claude Code stores sessions here, keyed by project path
PROJECT_KEY = "c--Users-george-grohwin-OneDrive---Smarsh--Inc-Documents-Dev-YTDigest"
SESSIONS_DIR = Path.home() / ".claude" / "projects" / PROJECT_KEY
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"

# UTC offset for display (US Eastern = -5; adjust if needed)
UTC_OFFSET_HOURS = -5


def parse_timestamp(ts_raw: str) -> str:
    """Convert ISO timestamp to local display string."""
    if not ts_raw:
        return ""
    try:
        dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        dt_local = dt + timedelta(hours=UTC_OFFSET_HOURS)
        return dt_local.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return ts_raw


def extract_text(content) -> str:
    """Extract readable text from a message content field."""
    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return str(content)

    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif not isinstance(block, dict):
            continue
        elif block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif block.get("type") == "tool_use":
            tool_name = block.get("name", "unknown")
            tool_input = block.get("input", {})
            if tool_name in ("Read", "Glob", "Grep"):
                detail = (
                    tool_input.get("file_path")
                    or tool_input.get("pattern")
                    or tool_input.get("path", "")
                )
                parts.append(f"> **Tool: {tool_name}** — {detail}")
            elif tool_name in ("Edit", "Write"):
                parts.append(
                    f"> **Tool: {tool_name}** — {tool_input.get('file_path', '')}"
                )
            elif tool_name == "Bash":
                cmd = tool_input.get("command", "")[:200]
                parts.append(f"> **Tool: Bash** — `{cmd}`")
            elif tool_name == "Agent":
                parts.append(f"> **Tool: Agent** — {tool_input.get('description', '')}")
            else:
                parts.append(f"> **Tool: {tool_name}**")

    return "\n".join(parts)


def list_sessions(full: bool = False):
    """Print available sessions with dates."""
    if not SESSIONS_DIR.exists():
        print(f"Sessions directory not found: {SESSIONS_DIR}")
        sys.exit(1)

    sessions = []
    for f in SESSIONS_DIR.glob("*.jsonl"):
        session_id = f.stem
        # Read first few lines to get date and first user message
        date_str = ""
        first_msg = ""
        with open(f, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    obj = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue
                if not date_str and obj.get("timestamp"):
                    date_str = parse_timestamp(obj["timestamp"])
                if (
                    not first_msg
                    and obj.get("type") == "user"
                    and not obj.get("isSidechain")
                ):
                    text = extract_text(obj.get("message", {}).get("content", ""))
                    # Skip tool results (automated user messages)
                    if obj.get("toolUseResult"):
                        continue
                    first_msg = text.strip().replace("\n", " ")[:120]

        sessions.append((date_str, session_id, first_msg))

    sessions.sort(reverse=True)

    print(f"{'Date':<22} {'Session ID':<40} ", end="")
    if full:
        print("First message")
    else:
        print()

    print("-" * (65 + (60 if full else 0)))
    for date_str, sid, msg in sessions:
        print(f"{date_str:<22} {sid:<40} ", end="")
        if full:
            print(msg[:60])
        else:
            print()


def export_session(session_id: str):
    """Convert a session JSONL to Markdown."""
    jsonl_path = SESSIONS_DIR / f"{session_id}.jsonl"
    if not jsonl_path.exists():
        print(f"Session file not found: {jsonl_path}")
        sys.exit(1)

    messages = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if obj.get("type") in ("file-history-snapshot", "queue-operation"):
                continue
            if "message" not in obj:
                continue
            if obj.get("isSidechain"):
                continue

            msg = obj["message"]
            role = msg.get("role") or obj.get("type")
            if not role:
                continue

            ts_str = parse_timestamp(obj.get("timestamp", ""))
            text = extract_text(msg.get("content", ""))

            if not text.strip():
                continue

            messages.append((role, text, ts_str))

    # Deduplicate consecutive identical messages
    deduped = []
    for role, text, ts in messages:
        if deduped and deduped[-1][0] == role and deduped[-1][1] == text:
            continue
        deduped.append((role, text, ts))

    # Determine session date from first timestamp
    session_date = ""
    for _, _, ts in deduped:
        if ts:
            session_date = ts.split(" ")[0]
            break

    # Build markdown
    lines = [f"# Session: {session_id}"]
    if session_date:
        lines.append(f"**Date:** {session_date}")
    lines.append(f"**Messages:** {len(deduped)}")
    lines.append("")

    for role, text, ts in deduped:
        label = "User" if role == "user" else "Assistant"
        ts_display = f" — *{ts}*" if ts else ""
        lines.append(f"## {label}{ts_display}\n")
        lines.append(f"{text}\n")

    # Write output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    short_id = session_id[:8]
    out_path = OUTPUT_DIR / f"session-{short_id}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")

    size_kb = out_path.stat().st_size / 1024
    print(f"Exported {len(deduped)} messages to {out_path} ({size_kb:.0f} KB)")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    if sys.argv[1] == "--list":
        full = "--full" in sys.argv
        list_sessions(full=full)
    else:
        export_session(sys.argv[1])


if __name__ == "__main__":
    main()
