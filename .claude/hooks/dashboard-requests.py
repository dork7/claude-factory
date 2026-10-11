#!/usr/bin/env python3
"""Dashboard requests: wakes the orchestrator when the dashboard asks for a ticket to move.

A Claude Code hook, registered in .claude/settings.json on SessionStart and Stop with
`asyncRewake`. It waits in the background until factory/requests.jsonl holds a request
that nobody has answered, then exits with code 2: Claude Code wakes the session and
shows it this hook's message.

Only one copy waits per project. It tells the session about each request once: one
that is still unanswered after that is picked up by the next /factory command, which
always handles waiting requests first. It stops when the session that started it ends.
"""
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: nothing wakes the session; /factory still handles requests.
    sys.exit(0)

POLL_SECONDS, MAX_HOURS = 2, 12


def waiting(requests):
    """The requests with no answer yet, oldest first."""
    asked, answered = [], set()
    try:
        lines = requests.read_text(encoding='utf-8').splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        (answered.add(entry.get('id')) if entry.get('done') else asked.append(entry))
    return [request for request in asked if request.get('id') not in answered]


def main():
    project = Path(os.environ.get('CLAUDE_PROJECT_DIR') or Path(__file__).resolve().parents[2]).resolve()
    requests = project / 'factory' / 'requests.jsonl'
    mine = Path(tempfile.gettempdir()) / ('claude-factory-' + hashlib.sha1(str(project).encode()).hexdigest()[:12])
    lock = open(mine.with_suffix('.lock'), 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0  # another copy is already waiting for this project
    told_file = mine.with_suffix('.told')
    started, parent = time.time(), os.getppid()
    while time.time() - started < MAX_HOURS * 3600 and os.getppid() == parent:
        told = set(told_file.read_text().split()) if told_file.exists() else set()
        new = [request for request in waiting(requests) if request.get('id') not in told]
        if new:
            told_file.write_text('\n'.join(sorted(told | {request['id'] for request in new})))
            what = ', '.join(f"{request['id']} ({request.get('action')} {request.get('job') or 'a backlog item'})" for request in new)
            print(f'The factory dashboard has {len(new)} request(s) waiting: {what}. '
                  'Act on them now as the factory orchestrator: read .claude/skills/factory/SKILL.md '
                  'and follow its section "Requests from the dashboard".', file=sys.stderr)
            return 2
        time.sleep(POLL_SECONDS)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:  # A failed watcher must never disturb the session.
        print(f'dashboard-requests: {error}', file=sys.stderr)
        sys.exit(0)
