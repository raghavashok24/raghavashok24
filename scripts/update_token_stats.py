#!/usr/bin/env python3
"""token usage — daily claude code token tracker.

tallies lifetime claude code token usage (via `ccusage`, falling back to
parsing the local ~/.claude logs), rewrites the stats table in README.md
between the TOKENS markers, and commits + pushes the result.

run daily via cron (crontab -e):
    0 21 * * * cd /path/to/profile-repo && python3 scripts/update_token_stats.py >> /tmp/token_stats.log 2>&1

flags:
    --no-git   update the readme only, skip commit/push (useful for testing)
"""
import datetime
import glob
import json
import os
import pathlib
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
README = REPO / "README.md"
START, END = "<!-- TOKENS:START -->", "<!-- TOKENS:END -->"


def usage_from_ccusage():
    """preferred source: the ccusage CLI (dedupes + aggregates properly)."""
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
    """fallback: parse claude code's local JSONL transcripts directly."""
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
        raise RuntimeError("no local claude code logs found")
    return days


def fmt(n):
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}b"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}m"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def build_table(days, today):
    seq = sorted((d, v) for d, v in days.items() if d != "unknown")
    total = sum(v for _, v in seq)
    n = len(seq)
    avg = total // max(1, n)
    peak_day, peak_val = max(seq, key=lambda kv: kv[1])
    return (
        "| total tokens used | days tracked | daily average | peak day | last updated |\n"
        "|---|---|---|---|---|\n"
        f"| {total:,} | {n} | {fmt(avg)} | {fmt(peak_val)} ({peak_day}) | {today} |"
    )


def update_readme(table):
    txt = README.read_text()
    if START not in txt or END not in txt:
        raise RuntimeError("TOKENS markers not found in README.md")
    head, rest = txt.split(START, 1)
    _, tail = rest.split(END, 1)
    README.write_text(f"{head}{START}\n{table}\n{END}{tail}")


def git_sync(total, today):
    subprocess.run(["git", "-C", str(REPO), "add", "README.md"], check=True)
    if subprocess.run(["git", "-C", str(REPO), "diff", "--cached", "--quiet"]).returncode == 0:
        print("no changes to commit")
        return
    subprocess.run(["git", "-C", str(REPO), "commit", "-m",
                    f"tokens: {total:,} ({today})"], check=True)
    for wait in (0, 2, 4, 8, 16):
        if wait:
            time.sleep(wait)
        push = subprocess.run(["git", "-C", str(REPO), "push"],
                              capture_output=True, text=True)
        if push.returncode == 0:
            return
        print(f"push failed, retrying:\n{push.stderr}", file=sys.stderr)
    print("warning: push failed after retries", file=sys.stderr)


def main():
    try:
        days = usage_from_ccusage()
        source = "ccusage"
    except Exception as e:
        print(f"ccusage unavailable ({e}); scanning local logs", file=sys.stderr)
        days = usage_from_logs()
        source = "local logs"
    total = sum(v for d, v in days.items() if d != "unknown")
    today = datetime.date.today().isoformat()
    update_readme(build_table(days, today))
    print(f"{total:,} tokens across {len(days)} days (source: {source})")
    if "--no-git" not in sys.argv:
        git_sync(total, today)


if __name__ == "__main__":
    main()
