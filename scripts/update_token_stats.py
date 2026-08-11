#!/usr/bin/env python3
"""Token Usage — daily Claude Code token tracker.

Tallies lifetime Claude Code token usage (via `ccusage`, falling back to
parsing the local ~/.claude logs), renders a plain-text stats block with an
ASCII progress bar and a daily-usage bar graph, writes it into README.md
between the TOKENS markers, and commits + pushes the result.

Run daily via cron:
    0 21 * * * cd /path/to/profile-repo && python3 scripts/update_token_stats.py

Flags:
    --no-git   update README only, skip commit/push (useful for testing)
"""
import datetime
import glob
import json
import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
README = REPO / "README.md"

RANKS = [
    (0, "TOKEN INITIATE"),
    (1_000_000, "PADAWAN PROMPTER"),
    (5_000_000, "CONTEXT CADET"),
    (10_000_000, "PROMPT OPERATOR"),
    (25_000_000, "AGENT WRANGLER"),
    (50_000_000, "CONTEXT ARCHITECT"),
    (100_000_000, "INFERENCE MACHINIST"),
    (250_000_000, "COMPUTE ARCHMAGE"),
    (500_000_000, "ASCENDANT"),
    (1_000_000_000, "TOKENMAXXER"),
    (10_000_000_000, "TOKENMAXXER INFINITY"),
]


def usage_from_ccusage():
    """Preferred source: the ccusage CLI (dedupes + aggregates properly)."""
    out = subprocess.run(
        ["npx", "-y", "ccusage@latest", "daily", "--json"],
        capture_output=True, text=True, timeout=300,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ccusage failed: {out.stderr[:200]}")
    data = json.loads(out.stdout)
    rows = data.get("daily") or data.get("days") or []
    days = {}
    for d in rows:
        date = d.get("date") or d.get("day")
        tot = d.get("totalTokens")
        if tot is None:
            tot = sum(v for k, v in d.items()
                      if isinstance(v, (int, float)) and k.lower().endswith("tokens"))
        if date:
            days[str(date)[:10]] = days.get(str(date)[:10], 0) + int(tot)
    if not days:
        raise RuntimeError("ccusage returned no rows")
    return days


def usage_from_logs():
    """Fallback: parse Claude Code's local JSONL transcripts directly."""
    days, seen = {}, set()
    for base in ("~/.claude/projects", "~/.config/claude/projects"):
        for fp in glob.glob(os.path.expanduser(base + "/**/*.jsonl"), recursive=True):
            try:
                fh = open(fp, errors="ignore")
            except OSError:
                continue
            with fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    msg = rec.get("message") or {}
                    u = msg.get("usage")
                    if not isinstance(u, dict):
                        continue
                    mid = msg.get("id") or rec.get("requestId") or rec.get("uuid")
                    if mid:
                        if mid in seen:
                            continue
                        seen.add(mid)
                    date = str(rec.get("timestamp") or "")[:10] or "unknown"
                    tot = sum(int(u.get(k) or 0) for k in (
                        "input_tokens", "output_tokens",
                        "cache_creation_input_tokens", "cache_read_input_tokens"))
                    days[date] = days.get(date, 0) + tot
    if not days:
        raise RuntimeError("no local Claude Code logs found")
    return days


def rank_for(total):
    cur, nxt = RANKS[0][1], None
    for threshold, name in RANKS:
        if total >= threshold:
            cur = name
        elif nxt is None:
            nxt = (threshold, name)
    return cur, nxt


def fmt(n):
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def build_block(total, days, today):
    cur, nxt = rank_for(total)
    lines = []
    lines.append(f"TOTAL CLAUDE CODE TOKENS : {total:,}")
    lines.append(f"CURRENT RANK             : {cur}")
    if nxt:
        lo = max(t for t, _ in RANKS if t <= total)
        pct = (total - lo) / (nxt[0] - lo)
        filled = max(1, round(pct * 30))
        bar = "#" * filled + "-" * (30 - filled)
        lines.append(f"NEXT RANK                : {nxt[1]} @ {fmt(nxt[0])}")
        lines.append(f"PROGRESS                 : [{bar}] {pct * 100:.1f}%")
    else:
        lines.append("RANK                     : MAXIMUM - TRUE TOKENMAXXER")
    lines.append("")
    lines.append("DAILY USAGE (LAST 14 DAYS)")
    seq = sorted((d, v) for d, v in days.items() if d != "unknown")[-14:]
    peak = max((v for _, v in seq), default=1) or 1
    for d, v in seq:
        blen = max(1, round(v / peak * 36))
        lines.append(f"{d} | {'#' * blen} {fmt(v)}")
    lines.append("")
    lines.append(f"LAST UPDATED {today}")
    return "```text\n" + "\n".join(lines) + "\n```"


def update_readme(block):
    txt = README.read_text()
    start, end = "<!-- TOKENS:START -->", "<!-- TOKENS:END -->"
    if start not in txt or end not in txt:
        raise RuntimeError("TOKENS markers not found in README.md")
    head, rest = txt.split(start, 1)
    _, tail = rest.split(end, 1)
    README.write_text(f"{head}{start}\n{block}\n{end}{tail}")


def git_sync(total, today):
    subprocess.run(["git", "-C", str(REPO), "add", "README.md"], check=True)
    if subprocess.run(["git", "-C", str(REPO), "diff", "--cached", "--quiet"]).returncode == 0:
        print("no changes to commit")
        return
    subprocess.run(["git", "-C", str(REPO), "commit", "-m",
                    f"tokens: {total:,} ({today})"], check=True)
    push = subprocess.run(["git", "-C", str(REPO), "push"], capture_output=True, text=True)
    if push.returncode != 0:
        print(f"warning: push failed:\n{push.stderr}", file=sys.stderr)


def main():
    try:
        days = usage_from_ccusage()
        source = "ccusage"
    except Exception as e:
        print(f"ccusage unavailable ({e}); scanning local logs", file=sys.stderr)
        days = usage_from_logs()
        source = "local logs"
    total = sum(days.values())
    today = datetime.date.today().isoformat()
    update_readme(build_block(total, days, today))
    print(f"{total:,} tokens across {len(days)} days (source: {source})")
    if "--no-git" not in sys.argv:
        git_sync(total, today)


if __name__ == "__main__":
    main()
