#!/usr/bin/env python3
"""token usage — daily claude code token tracker.

tallies lifetime claude code token usage (via `ccusage`, falling back to
parsing the local ~/.claude logs), renders assets/tokens.svg — a line graph
of cumulative tokens over time — plus a stats table in README.md between
the TOKENS markers, and commits + pushes the result.

run daily via cron:
    0 21 * * * cd /path/to/profile-repo && python3 scripts/update_token_stats.py

flags:
    --no-git   update files only, skip commit/push (useful for testing)
"""
import datetime
import glob
import json
import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
README = README_PATH = REPO / "README.md"
SVG = REPO / "assets" / "tokens.svg"

CYAN = "#00E5FF"
BG = "#070d1c"
GRIDC = "#1c2a44"
TXT = "#8fa7c4"


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


def render_chart(days):
    """line graph of cumulative total tokens over time, cyber-styled."""
    W, H = 760, 380
    L, R, T, B = 80, 36, 42, 56
    pw, ph = W - L - R, H - T - B

    seq = sorted((d, v) for d, v in days.items() if d != "unknown")
    cum, run = [], 0
    for d, v in seq:
        run += v
        cum.append((d, run))
    top = cum[-1][1] * 1.08

    def X(i):
        return L + (pw * i / max(1, len(cum) - 1))

    def Y(v):
        return T + ph - (ph * v / top)

    pts = [(X(i), Y(v)) for i, (_, v) in enumerate(cum)]
    if len(pts) == 1:
        pts = [(L, pts[0][1]), (L + pw, pts[0][1])]  # single day: flat line across

    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{L},{T + ph} " + line + f" {L + pw},{T + ph}"

    grid, ylabels = [], []
    for i in range(5):
        v = top * i / 4
        y = Y(v)
        grid.append(f'<line x1="{L}" y1="{y:.1f}" x2="{L + pw}" y2="{y:.1f}" stroke="{GRIDC}" stroke-width="1"/>')
        ylabels.append(f'<text x="{L - 10}" y="{y + 4:.1f}" text-anchor="end" fill="{TXT}" font-size="12">{fmt(v)}</text>')

    xlabels = []
    idxs = sorted({0, len(cum) // 2, len(cum) - 1})
    for i in idxs:
        xlabels.append(f'<text x="{X(i):.1f}" y="{T + ph + 24}" text-anchor="middle" fill="{TXT}" font-size="12">{cum[i][0]}</text>')

    dots = "" if len(cum) == 1 else "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{CYAN}"/>'
        for x, y in [(X(i), Y(v)) for i, (_, v) in enumerate(cum)])
    ex, ey = pts[-1]

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="total claude code tokens over time">
<defs>
  <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{CYAN}" stop-opacity="0.30"/>
    <stop offset="1" stop-color="{CYAN}" stop-opacity="0"/>
  </linearGradient>
  <filter id="glow" x="-30%" y="-30%" width="160%" height="160%">
    <feDropShadow dx="0" dy="0" stdDeviation="3" flood-color="{CYAN}" flood-opacity="0.7"/>
  </filter>
</defs>
<rect width="{W}" height="{H}" fill="{BG}" rx="10"/>
<rect x="1.5" y="1.5" width="{W - 3}" height="{H - 3}" fill="none" stroke="{CYAN}" stroke-opacity="0.25" stroke-width="1.5" rx="9"/>
<g font-family="ui-monospace,Menlo,monospace">
  <text x="{L}" y="28" fill="#ffffff" font-size="15" letter-spacing="2">total tokens over time</text>
  {"".join(grid)}
  {"".join(ylabels)}
  {"".join(xlabels)}
  <polygon points="{area}" fill="url(#area)"/>
  <polyline points="{line}" fill="none" stroke="{CYAN}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" filter="url(#glow)"/>
  {dots}
  <circle cx="{ex:.1f}" cy="{ey:.1f}" r="5" fill="{CYAN}" filter="url(#glow)"/>
  <text x="{min(ex, L + pw - 60):.1f}" y="{max(ey - 14, T + 14):.1f}" text-anchor="middle" fill="#ffffff" font-size="14" font-weight="bold">{fmt(cum[-1][1])}</text>
</g>
</svg>'''


def build_block(total, days, today):
    seq = sorted((d, v) for d, v in days.items() if d != "unknown")
    n = len(seq)
    avg = total // max(1, n)
    peak_day, peak_val = max(seq, key=lambda kv: kv[1])
    return f'''| total tokens used | days tracked | daily average | peak day | last updated |
|---|---|---|---|---|
| {total:,} | {n} | {fmt(avg)} | {fmt(peak_val)} ({peak_day}) | {today} |

![total claude code tokens over time](assets/tokens.svg)'''


def update_readme(block):
    txt = README.read_text()
    start, end = "<!-- TOKENS:START -->", "<!-- TOKENS:END -->"
    if start not in txt or end not in txt:
        raise RuntimeError("TOKENS markers not found in README.md")
    head, rest = txt.split(start, 1)
    _, tail = rest.split(end, 1)
    README.write_text(f"{head}{start}\n{block}\n{end}{tail}")


def git_sync(total, today):
    subprocess.run(["git", "-C", str(REPO), "add", "README.md", "assets/tokens.svg"], check=True)
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
    SVG.parent.mkdir(parents=True, exist_ok=True)
    SVG.write_text(render_chart(days))
    update_readme(build_block(total, days, today))
    print(f"{total:,} tokens across {len(days)} days (source: {source})")
    if "--no-git" not in sys.argv:
        git_sync(total, today)


if __name__ == "__main__":
    main()
