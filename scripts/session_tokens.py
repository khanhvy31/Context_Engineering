"""Show token usage for Claude Code sessions in this project folder.

Claude Code saves each session as a JSONL file under
    ~/.claude/projects/<encoded-project-path>/<session-id>.jsonl
where <encoded-project-path> is the absolute project path with every
non-alphanumeric character replaced by "-".

Usage:
    python scripts/session_tokens.py            # most recent session
    python scripts/session_tokens.py --all      # last 5 sessions, side by side
    python scripts/session_tokens.py --all -n 10
    python scripts/session_tokens.py --project /path/to/project
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
USAGE_FIELDS = ("input_tokens", "output_tokens",
                "cache_creation_input_tokens", "cache_read_input_tokens")


def encode_project_path(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def find_project_log_dir(project):
    candidate = PROJECTS_DIR / encode_project_path(project)
    if candidate.is_dir():
        return candidate
    # Fall back to a case-insensitive match (macOS paths can differ in case).
    wanted = encode_project_path(project).lower()
    if PROJECTS_DIR.is_dir():
        for d in PROJECTS_DIR.iterdir():
            if d.is_dir() and d.name.lower() == wanted:
                return d
    return None


def to_int(value):
    return value if isinstance(value, int) else 0


def parse_jsonl(path, stats):
    """Accumulate usage from one JSONL file into stats.

    One API response can be written as several 'assistant' lines that share the
    same message.id and repeat the same usage object, so usage is counted once per
    message.id (keeping the largest value seen for each field).
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return

    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue

        ts = entry.get("timestamp")
        if isinstance(ts, str):
            stats["first_ts"] = min(stats["first_ts"] or ts, ts)
            stats["last_ts"] = max(stats["last_ts"] or ts, ts)
        if entry.get("gitBranch") and not stats["branch"]:
            stats["branch"] = entry["gitBranch"]

        message = entry.get("message")
        if not isinstance(message, dict):
            continue

        if entry.get("type") == "user" and stats["prompt"] is None:
            text = first_text(message.get("content"))
            if text and not text.startswith(("<", "## Context Usage")):
                stats["prompt"] = text

        if entry.get("type") != "assistant":
            continue

        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                    stats["final_text"] = block["text"]
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    stats["tool_ids"].add(block.get("id") or id(block))

        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        msg_id = message.get("id") or entry.get("uuid") or str(len(stats["messages"]))
        if message.get("model") and not message["model"].startswith("<"):
            stats["model"] = message["model"]
        prev = stats["messages"].get(msg_id, {})
        stats["messages"][msg_id] = {
            f: max(to_int(usage.get(f)), prev.get(f, 0)) for f in USAGE_FIELDS
        }
        stats["order"].append(msg_id)


def first_text(content):
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return str(block.get("text", "")).strip()
    return None


def extract_answer(text):
    """Pull the headline rate and hit/missed verdict out of Claude's final reply."""
    if not text:
        return "?"
    rate = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    verdict = re.search(r"\b(didn't hit|did not hit|not hit|missed|misses|miss|hit)\b",
                        text, re.IGNORECASE)
    parts = []
    if rate:
        parts.append(rate.group(1) + "%")
    if verdict:
        parts.append("HIT" if verdict.group(1).lower() == "hit" else "MISSED")
    return " ".join(parts) or "?"


def new_stats():
    return {"messages": {}, "order": [], "tool_ids": set(), "branch": None, "final_text": None,
            "model": None, "prompt": None, "first_ts": None, "last_ts": None}


def summarize(session_file):
    main = new_stats()
    parse_jsonl(session_file, main)

    # Subagent transcripts (if any) live next to the session file.
    sub = new_stats()
    sub_dir = session_file.with_suffix("")
    sub_files = sorted(sub_dir.rglob("*.jsonl")) if sub_dir.is_dir() else []
    for f in sub_files:
        parse_jsonl(f, sub)

    def totals(stats):
        t = {f: sum(m[f] for m in stats["messages"].values()) for f in USAGE_FIELDS}
        t["total"] = sum(t[f] for f in USAGE_FIELDS)
        t["turns"] = len(stats["messages"])
        t["tool_calls"] = len(stats["tool_ids"])
        return t

    main_t = totals(main)
    sub_t = totals(sub)
    last_context = 0
    if main["order"]:
        last = main["messages"][main["order"][-1]]
        last_context = (last["input_tokens"] + last["cache_creation_input_tokens"]
                        + last["cache_read_input_tokens"])

    return {
        "file": session_file,
        "session": session_file.stem,
        "branch": main["branch"] or "?",
        "model": main["model"] or "?",
        "prompt": main["prompt"] or "",
        "answer": extract_answer(main["final_text"]),
        "started": main["first_ts"],
        "main": main_t,
        "sub": sub_t,
        "subagent_files": len(sub_files),
        "last_context": last_context,
    }


def fmt_num(n):
    return f"{n:,}"


def fmt_time(ts):
    if not ts:
        return "?"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return ts[:16]


def print_single(s):
    m, sub = s["main"], s["sub"]
    print(f"Session:  {s['session']}")
    print(f"Started:  {fmt_time(s['started'])}   Branch: {s['branch']}   Model: {s['model']}")
    if s["prompt"]:
        print(f"Prompt:   {shorten(s['prompt'], 70)}")
    print(f"Answer:   {s['answer']}")
    print()
    rows = [
        ("Input tokens", "input_tokens"),
        ("Output tokens", "output_tokens"),
        ("Cache creation tokens", "cache_creation_input_tokens"),
        ("Cache read tokens", "cache_read_input_tokens"),
        ("Total tokens", "total"),
        ("Assistant turns", "turns"),
        ("Tool calls", "tool_calls"),
    ]
    has_sub = s["subagent_files"] > 0
    header = f"{'':24}{'main':>14}"
    if has_sub:
        header += f"{'subagents':>14}{'combined':>14}"
    print(header)
    print("-" * len(header))
    for label, key in rows:
        line = f"{label:24}{fmt_num(m[key]):>14}"
        if has_sub:
            line += f"{fmt_num(sub[key]):>14}{fmt_num(m[key] + sub[key]):>14}"
        print(line)
    print()
    print(f"Context size at last turn (main): {fmt_num(s['last_context'])} tokens")


def print_table(summaries):
    cols = [
        ("Started", lambda s: fmt_time(s["started"])),
        ("Branch", lambda s: shorten(s["branch"], 14)),
        ("Input", lambda s: fmt_num(s["main"]["input_tokens"] + s["sub"]["input_tokens"])),
        ("Output", lambda s: fmt_num(s["main"]["output_tokens"] + s["sub"]["output_tokens"])),
        ("Cache write", lambda s: fmt_num(s["main"]["cache_creation_input_tokens"]
                                          + s["sub"]["cache_creation_input_tokens"])),
        ("Cache read", lambda s: fmt_num(s["main"]["cache_read_input_tokens"]
                                         + s["sub"]["cache_read_input_tokens"])),
        ("Total", lambda s: fmt_num(s["main"]["total"] + s["sub"]["total"])),
        ("Turns", lambda s: fmt_num(s["main"]["turns"] + s["sub"]["turns"])),
        ("Tools", lambda s: fmt_num(s["main"]["tool_calls"] + s["sub"]["tool_calls"])),
        ("Last ctx", lambda s: fmt_num(s["last_context"])),
        ("Answer", lambda s: s["answer"]),
        ("Session", lambda s: s["session"][:8]),
    ]
    table = [[name for name, _ in cols]] + [[fn(s) for _, fn in cols] for s in summaries]
    widths = [max(len(row[i]) for row in table) for i in range(len(cols))]
    for i, row in enumerate(table):
        print("  ".join(cell.rjust(widths[j]) if 2 <= j < len(cols) - 2 else cell.ljust(widths[j])
                        for j, cell in enumerate(row)))
        if i == 0:
            print("  ".join("-" * w for w in widths))
    print()
    print("Totals include subagent usage. 'Last ctx' = context size at the final main turn.")
    for s in summaries:
        if s["prompt"]:
            print(f"  {s['session'][:8]}: {shorten(s['prompt'], 80)}")


def shorten(text, width):
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 3] + "..."


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--all", action="store_true", help="list recent sessions side by side")
    parser.add_argument("-n", type=int, default=5, help="number of sessions for --all (default 5)")
    parser.add_argument("--project", default=None,
                        help="project folder (default: the repo containing this script)")
    args = parser.parse_args()

    project = Path(args.project).resolve() if args.project else Path(__file__).resolve().parent.parent
    log_dir = find_project_log_dir(project)
    if log_dir is None:
        print(f"No Claude Code logs found for {project}")
        print(f"(looked in {PROJECTS_DIR / encode_project_path(project)})")
        sys.exit(1)

    files = sorted(log_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        print(f"No session files in {log_dir}")
        sys.exit(1)

    if args.all:
        summaries = [summarize(f) for f in files[: max(args.n, 1)]]
        summaries.reverse()  # oldest first, so Run A appears above Run B
        print_table(summaries)
    else:
        print_single(summarize(files[0]))


if __name__ == "__main__":
    main()
