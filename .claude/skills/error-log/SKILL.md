---
name: error-log
description: Log each error that needed a fix, with its cause and the solution that was implemented, in factory/errors.jsonl, and search that log before debugging. Use when a command, build, test, type check or tool fails and you change something to get past it, when a failure can't be solved, and before you start debugging any failure.
---

# Error Log

A shared record of the errors this project has hit and what fixed them, so the same
error is solved once. Everything goes through one script:

```bash
python3 .claude/skills/error-log/log.py search <words>   # before you debug
python3 .claude/skills/error-log/log.py add ...          # after you solve it
```

The log is `factory/errors.jsonl`, one entry per line. Never write to it by hand.

## Before You Debug

Search for the part of the error that will not change between runs: the error code, the
exception name, or a distinctive phrase.

```bash
python3 .claude/skills/error-log/log.py search TS2322 calendar
```

It prints the entries that contain every word, newest first. If one matches, try its
solution first.

## What to Log

Log an error when:

- A command, build, test run, type check or tool call failed, and you had to change
  something to get past it.
- The same failure came back after you thought it was fixed.
- You could not solve it. Log it as `unsolved`, with what you tried.

Do not log:

- A test you just wrote failing before its implementation exists.
- A slip you corrected on the next line, such as a typo or a wrong path.
- A command that is meant to exit non-zero, such as a `grep` with no match.
- A review finding. Those belong in the review file.

Write one entry per error, when you know how it ended, so the entry holds the solution
and not a guess.

## How to Log

```bash
python3 .claude/skills/error-log/log.py add \
  --agent builder \
  --job 003-rate-limiting \
  --where "npm test, tests/limits.test.ts:41" \
  --error "TypeError: Cannot read properties of undefined (reading 'windowMs')" \
  --cause "The limiter was built before the config was loaded, so its options were undefined." \
  --solution "Build the limiter inside startServer(), after loadConfig() has run." \
  --files src/server.ts src/limits.ts \
  --status solved
```

| Field | Required | What goes in it |
|---|---|---|
| `--agent` | yes | Your agent name, or `orchestrator`. |
| `--error` | yes | The error text as it appeared, trimmed to the lines that identify it. |
| `--solution` | yes | What you changed that made it go away. For `unsolved`, what you tried. |
| `--cause` | no | Why it happened, if you found out. Leave it out and never guess. |
| `--job` | no | The factory job id, if there is one. |
| `--where` | no | The command that failed, or the `path:line`. |
| `--files` | no | The files the solution changed. |
| `--status` | no | `solved` (the default), `worked-around` or `unsolved`. |
| `--same-as` | no | The id of an earlier entry, when this is that error again. |

- `solved`: the cause is gone.
- `worked-around`: the error no longer appears, and the cause is still there. Say what
  is left in `--solution`.
- `unsolved`: it still fails.

When a search found the same error and its solution worked again, still add an entry,
with `--same-as <id>`. An error that keeps coming back is something the project should
fix for good or write down in `CLAUDE.md`.

## Rules

- Record what happened, not what should have. The solution is the change you made and
  saw working.
- Never put a secret, a token or personal data in an entry. Replace it with `<redacted>`.
- Keep it short: an entry is for the next reader with the same error in front of them.
- Logging is not fixing, and it is not a report. Your own output file still says what
  you did.
