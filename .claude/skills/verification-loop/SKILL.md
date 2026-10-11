---
name: verification-loop
description: Verify a change before handing it on. Runs the project's build, type check, lint and tests, scans the change for secrets and debug output, reads the diff, and ends in one report. Use after finishing a feature or a fix, before a review or a merge, and after a refactor.
---

# Verification Loop

One definition of "verified", for everyone who has to say that a change works.

## When to Use

- After completing a feature or a significant code change
- Before handing work to a reviewer, and before a merge
- After a refactor or a cleanup
- Again after each significant change during long work, not only at the end

## Commands

Use the project's own commands, looked up in this order:

1. Project facts in `CLAUDE.md`: the test command, and any build, type-check or lint
   command listed there.
2. The project's manifest: the scripts in `package.json`, a `Makefile`, `pyproject.toml`
   or whatever the stack uses.

A phase the project has no command for is `n/a`. Never invent a command, install a tool
or fetch one with `npx` to fill a phase.

`<base>` below is the branch the change will merge into: `main` in the software factory.

## Verification Phases

### Phase 1: Build

Run the build command and read the end of its output.

If the build fails, stop: report the errors and mark the later phases `not run`.

### Phase 2: Type Check

Run the type checker over the whole project, not only the files that changed. Report
every error as `path:line`.

### Phase 3: Lint

Run the linter. Errors fail the phase. Warnings are reported and do not fail it.

### Phase 4: Test Suite

Run the whole suite once. Report:

- Total tests: X
- Passed: X
- Failed: X
- Coverage: X%, if the project measures it. A threshold applies only if `CLAUDE.md` sets one.

### Phase 5: Security Scan

Look only at what the change touches:

```bash
# The files this change touches
git diff --name-only <base>...HEAD

# Likely secrets in the lines it adds
git diff <base>...HEAD | grep -nE "^\+.*(api[_-]?key|secret|password|token)[\"']?\s*[:=]\s*[\"'][^\"']{8,}" | head -20

# Debug output it leaves behind
git diff <base>...HEAD | grep -nE "^\+.*(console\.log|debugger|print\()" | head -20
```

A match is a lead and not a verdict: read the line. Debug output fails the phase only
where the project's conventions forbid it.

### Phase 6: Diff Review

```bash
git diff --stat <base>...HEAD
```

Read each changed file for:

- Changes nobody asked for
- Missing error handling
- Edge cases the tests do not reach
- Leftover TODOs, commented-out code and stray files

## Output Format

After the phases, produce this report:

```
VERIFICATION REPORT
==================

Build:     [PASS/FAIL/n/a]
Types:     [PASS/FAIL/n/a] (X errors)
Lint:      [PASS/FAIL/n/a] (X errors, Y warnings)
Tests:     [PASS/FAIL/n/a] (X/Y passed, Z% coverage)
Security:  [PASS/FAIL] (X issues)
Diff:      [X files changed]

Overall:   [READY/NOT READY]

Issues to Fix:
1. ...
2. ...
```

## Rules

- Report only what you saw. For a failing phase, quote the lines of real output that
  show it. A phase you did not run is `not run` or `n/a`, never `PASS`.
- `READY` means no phase is `FAIL`. One failing phase makes the whole report `NOT READY`.
- Verifying is not fixing. If you were asked to verify, report. If you own the change,
  fix what the report lists and run the loop again.

## Integration with Hooks

The hook in `.claude/hooks/format-typecheck.py` formats and type-checks each file as it
is edited. It catches problems early, one file at a time. This loop is the full pass
over the whole change.
