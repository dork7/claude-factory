# claude-factory

## Project facts

Every factory agent relies on this section. Keep it true.

- Language: none yet.
- Test command: none yet.
- Conventions: none yet.

The first job's spec chooses the stack. The builder that implements it replaces these
three lines with the real language, test command and conventions, on its branch, so
the facts merge together with the code they describe.

## Software factory

Features are built by `/factory` (see `.claude/skills/factory/SKILL.md`). Its working
files live in `factory/`; only `factory/dashboard.html` and `factory/serve.py` are tracked
by git. Start the dashboard with `python3 factory/serve.py`. Its Move and Start buttons
ask the orchestrator to move a ticket on; they change nothing themselves.

Two hooks in `.claude/hooks/` log every agent run: `token-inspector.py` writes the
tokens to `factory/tokens.jsonl`, and `message-log.py` writes what the agents say to
each other to `factory/messages.jsonl`. The dashboard shows both. A third hook,
`format-typecheck.py`, runs after every edit: it formats the file with Prettier and
type-checks it with `tsc`, when the project has those installed, and tells the agent
what it found.

Agents record the errors they hit and the solutions they implemented in
`factory/errors.jsonl`, through the `error-log` skill, and search it before debugging.
After every merge the `auditor` agent grades how each agent did and keeps a scorecard
in `factory/audit.md`. The dashboard shows both.
