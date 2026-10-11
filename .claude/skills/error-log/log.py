#!/usr/bin/env python3
"""Error log: the errors agents hit and the solutions they implemented.

Kept in factory/errors.jsonl, one entry per line. See SKILL.md beside this file.

  log.py add --agent NAME --error TEXT --solution TEXT [--cause TEXT] [--job ID]
             [--where TEXT] [--files PATH ...] [--status solved|worked-around|unsolved]
             [--same-as ID]
  log.py search WORD [WORD ...]    entries that contain every word, newest first
  log.py list [--job ID]           every entry, newest first
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: no lock, so two agents logging at once may share an id.
    fcntl = None

LOG = Path(__file__).resolve().parents[3] / 'factory' / 'errors.jsonl'
STATUSES = ('solved', 'worked-around', 'unsolved')
TEXT_LIMIT, SHOWN = 2000, 20


def read(lines):
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries


def entries():
    return read(LOG.read_text(encoding='utf-8').splitlines()) if LOG.exists() else []


def add(given):
    for name in ('agent', 'error', 'solution'):
        if not getattr(given, name).strip():
            sys.exit(f'--{name} is empty')
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, 'a+', encoding='utf-8') as log:
        if fcntl:
            fcntl.flock(log, fcntl.LOCK_EX)
        log.seek(0)
        known = {entry.get('id') for entry in read(log)}
        if given.same_as and given.same_as not in known:
            sys.exit(f'--same-as {given.same_as}: no such entry')
        entry = {
            'id': f'E{len(known) + 1:03d}',
            'ts': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),
            'job': given.job, 'agent': given.agent.strip(), 'status': given.status,
            'where': given.where, 'error': given.error.strip()[:TEXT_LIMIT],
            'cause': given.cause and given.cause.strip()[:TEXT_LIMIT],
            'solution': given.solution.strip()[:TEXT_LIMIT],
            'files': given.files, 'same_as': given.same_as,
        }
        log.write(json.dumps(entry) + '\n')
    print(f"logged {entry['id']}")


def show(found):
    for entry in found[:SHOWN]:
        again = f" (same as {entry['same_as']})" if entry.get('same_as') else ''
        print(f"{entry.get('id')}  {str(entry.get('ts'))[:10]}  {entry.get('agent')}  "
              f"{entry.get('job') or 'no job'}  [{entry.get('status')}]{again}")
        for name in ('where', 'error', 'cause', 'solution'):
            if entry.get(name):
                print(f'  {name + ":":<10}{entry[name]}')
        if entry.get('files'):
            print(f"  {'files:':<10}{', '.join(entry['files'])}")
        print()
    if len(found) > SHOWN:
        print(f'... and {len(found) - SHOWN} older entries')
    if not found:
        print('no entries')


def main():
    parser = argparse.ArgumentParser(description='The errors agents hit and the solutions they implemented.')
    commands = parser.add_subparsers(dest='command', required=True)
    adding = commands.add_parser('add', help='log one error and its solution')
    adding.add_argument('--agent', required=True)
    adding.add_argument('--error', required=True)
    adding.add_argument('--solution', required=True)
    adding.add_argument('--cause')
    adding.add_argument('--job')
    adding.add_argument('--where')
    adding.add_argument('--files', nargs='*', default=[])
    adding.add_argument('--status', choices=STATUSES, default='solved')
    adding.add_argument('--same-as', dest='same_as')
    searching = commands.add_parser('search', help='entries that contain every word')
    searching.add_argument('words', nargs='+')
    listing = commands.add_parser('list', help='every entry, newest first')
    listing.add_argument('--job')
    given = parser.parse_args()

    if given.command == 'add':
        return add(given)
    newest_first = entries()[::-1]
    if given.command == 'search':
        words = [word.lower() for word in given.words]
        text = lambda entry: ' '.join(str(value) for value in entry.values()).lower()
        return show([entry for entry in newest_first if all(word in text(entry) for word in words)])
    show([entry for entry in newest_first if not given.job or entry.get('job') == given.job])


if __name__ == '__main__':
    main()
