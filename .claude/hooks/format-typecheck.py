#!/usr/bin/env python3
"""Format and type-check: runs after every Edit or Write, on the file that was changed.

A Claude Code hook, registered in .claude/settings.json on PostToolUse for Edit|Write.
It covers JavaScript and TypeScript:

  format      Prettier rewrites the file, if the project has Prettier both installed
              and configured. The agent is told when the file changed under it.
  type check  for a TypeScript file, `tsc --noEmit` on its project. The agent is shown
              the errors in that file.

It runs only what is already in the project's node_modules, never npx, so it installs
nothing and does nothing in a project without these tools. It never fails an edit:
whatever it finds is added to the agent's context beside the tool result.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

FORMATTED = {'.ts', '.tsx', '.mts', '.cts', '.js', '.jsx', '.mjs', '.cjs'}
TYPE_CHECKED = {'.ts', '.tsx', '.mts', '.cts'}
# The factory's own files and anything vendored are not the project's code.
SKIPPED = {'factory', '.claude', '.git', 'node_modules', 'dist'}
FORMAT_SECONDS, TYPE_CHECK_SECONDS, MAX_ERRORS = 20, 60, 10


def folders(file, project):
    """The file's folder and each one above it, up to and including the project's root."""
    folder = file.parent
    while True:
        yield folder
        if folder == project or folder == folder.parent:
            return
        folder = folder.parent


def local_tool(name, file, project):
    """A tool from the nearest node_modules, and the folder that node_modules is in."""
    for folder in folders(file, project):
        found = shutil.which(name, path=str(folder / 'node_modules' / '.bin'))
        if found:
            return found, folder
    return None, None


def prettier_is_configured(file, project):
    for folder in folders(file, project):
        if any(folder.glob('.prettierrc*')) or any(folder.glob('prettier.config.*')):
            return True
        try:
            if 'prettier' in json.loads((folder / 'package.json').read_text(encoding='utf-8')):
                return True
        except (OSError, ValueError):
            pass
    return False


def run(command, folder, seconds):
    """The finished command, or None if it could not run or ran out of time."""
    try:
        return subprocess.run(command, cwd=folder, capture_output=True, text=True, timeout=seconds)
    except (OSError, subprocess.TimeoutExpired):
        return None


def format_file(file, project, name):
    prettier, folder = local_tool('prettier', file, project)
    if not prettier or not prettier_is_configured(file, project):
        return None
    before = file.read_bytes()
    done = run([prettier, '--write', str(file)], folder, FORMAT_SECONDS)
    if done is None:
        return None
    if done.returncode != 0:
        why = (done.stderr or done.stdout).strip().splitlines()[:5]
        return f'Prettier could not format {name}:\n' + '\n'.join(why)
    if file.read_bytes() != before:
        return f'Prettier reformatted {name}. Read it again before your next edit to it.'
    return None


def type_check(file, project, name):
    tsc, _ = local_tool('tsc', file, project)
    root = next((folder for folder in folders(file, project) if (folder / 'tsconfig.json').exists()), None)
    if not tsc or not root:
        return None
    done = run([tsc, '--noEmit', '--pretty', 'false'], root, TYPE_CHECK_SECONDS)
    if done is None:
        return None
    # tsc names files relative to the folder it ran in: `src/a.ts(12,5): error TS2322: ...`
    here = file.relative_to(root).as_posix() + '('
    errors = [line for line in done.stdout.splitlines() if line.startswith(here)]
    if not errors:
        return None
    more = f'\n... and {len(errors) - MAX_ERRORS} more' if len(errors) > MAX_ERRORS else ''
    return f'tsc reports {len(errors)} type error(s) in {name}:\n' + '\n'.join(errors[:MAX_ERRORS]) + more


def main():
    payload = json.load(sys.stdin)
    project = Path(os.environ.get('CLAUDE_PROJECT_DIR') or payload.get('cwd') or '.').resolve()
    file = Path((payload.get('tool_input') or {}).get('file_path') or '').resolve()
    if not file.is_file() or project not in file.parents:
        return
    inside = file.relative_to(project)
    if inside.parts[0] in SKIPPED:
        return
    name = inside.as_posix()
    notes = [
        format_file(file, project, name) if file.suffix in FORMATTED else None,
        type_check(file, project, name) if file.suffix in TYPE_CHECKED else None,
    ]
    notes = [note for note in notes if note]
    if notes:
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'PostToolUse', 'additionalContext': '\n\n'.join(notes)}}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:  # A failed check must never fail the edit it follows.
        print(f'format-typecheck: {error}', file=sys.stderr)
    sys.exit(0)
