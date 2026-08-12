# daily token tracker — local setup

Auto-updates the token table in your profile README every day, based on your
lifetime Claude Code token usage, then commits + pushes the change.

## what's in this zip

- `scripts/update_token_stats.py` — the updated script. Counts tokens (via the
  `ccusage` CLI, falling back to parsing your local `~/.claude` logs), rewrites
  the table between the `<!-- TOKENS:START -->` / `<!-- TOKENS:END -->` markers
  in `README.md`, and commits + pushes only when the numbers changed.
- `README-snippet.md` — the marker block your README needs (yours already has
  it; this is just for reference / in case you ever rebuild the README).
- `SETUP.md` — this file.

## requirements

- Python 3.8+ (`python3 --version`)
- Node.js / `npx` (for `ccusage`; optional — the script falls back to reading
  `~/.claude/projects/**/*.jsonl` directly if it's missing)
- A local clone of `raghavashok24/raghavashok24` that can `git push` without
  prompting (SSH key, or HTTPS with cached credentials / `gh auth login`)

## install

1. Copy `scripts/update_token_stats.py` into your profile repo, replacing the
   old one:

   ```bash
   cp scripts/update_token_stats.py /path/to/raghavashok24/scripts/
   ```

2. Dry-run it first (updates the README locally, no commit/push):

   ```bash
   cd /path/to/raghavashok24
   python3 scripts/update_token_stats.py --no-git
   git diff README.md   # check the table looks right, then discard or keep
   ```

3. Full run (updates + commits + pushes):

   ```bash
   python3 scripts/update_token_stats.py
   ```

## schedule it daily

This must run on your own machine — your token data lives in the local
`~/.claude` logs, so GitHub Actions can't do it.

### macOS / Linux (cron)

```bash
crontab -e
```

Add one line (9pm daily; adjust the time and paths):

```
0 21 * * * cd /path/to/raghavashok24 && /usr/bin/python3 scripts/update_token_stats.py >> /tmp/token_stats.log 2>&1
```

Check `which python3` for the right interpreter path, and `tail
/tmp/token_stats.log` after the first scheduled run to confirm it worked.

macOS note: cron only fires while the machine is awake. If your laptop is
usually asleep at the scheduled time, either pick a time you're normally
working, or use launchd with `StartCalendarInterval` (launchd runs a missed
job at next wake, cron does not).

### Windows (Task Scheduler)

Task Scheduler → Create Basic Task → Daily → Action "Start a program":

- Program: `python`
- Arguments: `scripts\update_token_stats.py`
- Start in: `C:\path\to\raghavashok24`

## troubleshooting

- **"TOKENS markers not found"** — your README is missing the
  `<!-- TOKENS:START -->` / `<!-- TOKENS:END -->` comments; paste the block
  from `README-snippet.md` where you want the table.
- **push fails in cron but works manually** — cron doesn't load your shell
  profile, so SSH agents/credential helpers may be missing. Easiest fix: use
  an SSH remote (`git remote set-url origin git@github.com:raghavashok24/raghavashok24.git`)
  with a passphrase-less key, or a credential store (`git config credential.helper store`).
- **ccusage errors** — fine to ignore; the script automatically falls back to
  parsing the local logs. The stderr line tells you which source was used.
