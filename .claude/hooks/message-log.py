#!/usr/bin/env python3
"""Message log: records what the agents say to each other in factory/messages.jsonl.

A Claude Code hook, registered in .claude/settings.json on SubagentStart, SubagentStop
and Stop. Every run reads the session's transcripts again and appends what is new:

  prompt  the orchestrator spawning an agent or sending it a message (Agent, SendMessage)
  reply   an agent handing its result back to the orchestrator (SubagentHandback)
  write   an agent writing or editing a file under factory/jobs/, which is how the
          factory's agents pass work to each other; `text` is the file's first line.
          A file written by a shell command is logged only if the command redirects
          into its factory/jobs/ path by name.

Each line carries the id of the tool call it came from, so nothing is logged twice.
Reads are not logged: agents mostly read files through shell commands, and a command
that names a file can't be told apart reliably from one that reads it.
factory/dashboard.html reads the file.

  python3 .claude/hooks/message-log.py --backfill [TRANSCRIPTS_DIR]
      log this project's past sessions (default: its folder in ~/.claude/projects)
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: no lock, so two hooks at once may log a message twice.
    fcntl = None

# A job id, from a spawn prompt (`Job 003-rate-limiting, round 2.`) or a job file's path.
JOB = re.compile(r'\bJob (\d{3}-[a-z0-9-]+)|factory/jobs/(\d{3}-[a-z0-9-]+)')
JOB_FILE = re.compile(r'(?:^|/)factory/jobs/(.+)$')
# A shell command writing a job file: `> path`, `>> path` or `tee path`, and the first
# line of the here-document that follows it, if there is one.
SHELL_WRITE = re.compile(r'''(?:>>?|\btee\s+(?:-a\s+)?)\s*["']?[^\s"'<>|;&()]*factory/jobs/([^\s"'<>|;&()]+)'''
                         r'''(?:["']?\s*<<-?\s*["']?\w+["']?[^\n]*\n([^\n]*))?''')
TEXT_LIMIT = 2000


def job_in(text):
    found = JOB.search(text or '')
    return found and (found.group(1) or found.group(2))


def prompt_text(message):
    """The text a user message carries, without tool results."""
    content = message.get('content')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return ' '.join(part.get('text', '') for part in content if isinstance(part, dict) and part.get('type') == 'text')
    return ''


def describe(call, agents, spawned):
    """What one tool call says to another agent: a list of log fields, usually one or none."""
    name, given = call.get('name'), call.get('input') or {}
    if name == 'Agent':
        return [{'kind': 'prompt', 'to': given.get('subagent_type') or given.get('name') or 'agent',
                 'agent_id': spawned.get(call.get('id')), 'text': given.get('prompt')}]
    if name == 'SendMessage':
        to = given.get('to') or given.get('recipient')
        return [{'kind': 'prompt', 'to': agents.get(to, to), 'agent_id': to if to in agents else None,
                 'text': given.get('message') or given.get('content')}]
    if name == 'SubagentHandback':
        return [{'kind': 'reply', 'to': 'orchestrator', 'text': given.get('message')}]
    if name in ('Write', 'Edit'):
        file = JOB_FILE.search(str(given.get('file_path') or ''))
        first_line = str(given.get('content') or '').strip().split('\n', 1)[0]
        return [{'kind': 'write', 'file': file.group(1), 'text': first_line}] if file else []
    if name == 'Bash':
        return [{'kind': 'write', 'file': file, 'text': first_line.strip()}
                for file, first_line in SHELL_WRITE.findall(str(given.get('command') or ''))]
    return []


def read_transcript(path, sender, sender_id, agents, spawned):
    """Everything one transcript's owner sent: the orchestrator (no id) or one agent."""
    sidechain, records, job = sender_id is not None, [], None
    with open(path, encoding='utf-8', errors='replace') as lines:
        for line in lines:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            message = entry.get('message')
            if bool(entry.get('isSidechain')) != sidechain or not isinstance(message, dict):
                continue
            if entry.get('type') == 'user':
                # An agent's first prompt names the job that everything it sends belongs to.
                if sidechain and job is None and not entry.get('isMeta'):
                    job = job_in(prompt_text(message))
                continue
            if entry.get('type') != 'assistant' or not isinstance(message.get('content'), list):
                continue
            for part in message['content']:
                if part.get('type') != 'tool_use':
                    continue
                for nth, said in enumerate(describe(part, agents, spawned)):
                    text = str(said.get('text') or '')
                    records.append({
                        'ts': entry.get('timestamp'),
                        'job': job_in(text) or job_in('factory/jobs/' + (said.get('file') or '')) or job,
                        'kind': said['kind'], 'from': sender, 'to': said.get('to'),
                        'agent_id': said.get('agent_id') or sender_id,
                        'text': text[:TEXT_LIMIT], 'file': said.get('file'),
                        'id': part.get('id') if nth == 0 else f"{part.get('id')}:{nth}",
                    })
    return records


class Log:
    """factory/messages.jsonl, held open and locked while this run reads and appends."""

    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(path, 'a+', encoding='utf-8')
        if fcntl:
            fcntl.flock(self.file, fcntl.LOCK_EX)
        self.ids, self.handed_back, self.added = set(), set(), 0
        self.file.seek(0)
        for line in self.file:
            try:
                self._remember(json.loads(line))
            except ValueError:
                continue

    def _remember(self, record):
        self.ids.add(record.get('id'))
        if record.get('kind') == 'reply' and not str(record.get('id')).startswith('last:'):
            self.handed_back.add(record.get('agent_id'))

    def add(self, session, records):
        for record in records:
            if record['id'] in self.ids:
                continue
            self.file.write(json.dumps({'session': session, **record}) + '\n')
            self._remember(record)
            self.added += 1
        self.file.flush()


def sweep(log, session, transcript):
    """Log what is new in one session: the orchestrator's transcript and every agent's."""
    folder = transcript.with_suffix('') / 'subagents'
    agents, spawned = {}, {}  # agent id -> its type, and the Agent call that spawned it -> its id
    for meta in folder.glob('agent-*.meta.json'):
        agent_id, facts = meta.name[len('agent-'):-len('.meta.json')], read_json(meta)
        agents[agent_id] = facts.get('agentType') or 'agent'
        spawned[facts.get('toolUseId')] = agent_id
    if transcript.exists():
        log.add(session, read_transcript(transcript, 'orchestrator', None, agents, spawned))
    for agent_transcript in sorted(folder.glob('agent-*.jsonl')):
        agent_id = agent_transcript.stem.removeprefix('agent-')
        log.add(session, read_transcript(agent_transcript, agents.get(agent_id, 'agent'), agent_id, agents, spawned))


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def main():
    project = Path(os.environ.get('CLAUDE_PROJECT_DIR') or Path(__file__).resolve().parents[2])
    log = Log(project / 'factory' / 'messages.jsonl')

    if '--backfill' in sys.argv:
        given = sys.argv[sys.argv.index('--backfill') + 1:]
        folder = Path(given[0]).expanduser() if given else (
            Path.home() / '.claude' / 'projects' / re.sub(r'[^A-Za-z0-9]', '-', str(project.resolve())))
        for transcript in sorted(folder.glob('*.jsonl')):
            sweep(log, transcript.stem, transcript)
        print(f'{log.added} lines added to {log.file.name} from {folder}')
        return

    payload = json.load(sys.stdin)
    transcript = Path(payload['transcript_path']).expanduser()
    session = payload.get('session_id') or transcript.stem
    sweep(log, session, transcript)

    # An agent that ended without a handback call still said something: keep its last words.
    agent_id = str(payload.get('agent_id') or '').removeprefix('agent-')
    last = payload.get('last_assistant_message')
    if payload.get('hook_event_name') == 'SubagentStop' and last and agent_id not in log.handed_back:
        log.add(session, [{
            'ts': datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'), 'job': job_in(last), 'kind': 'reply', 'from': payload.get('agent_type') or 'agent',
            'to': 'orchestrator', 'agent_id': agent_id, 'text': last[:TEXT_LIMIT], 'file': None,
            'id': f"last:{agent_id}:{hashlib.sha1(last.encode()).hexdigest()[:12]}",
        }])


if __name__ == '__main__':
    try:
        main()
    except Exception as error:  # A logging failure must never stop or block an agent.
        print(f'message-log: {error}', file=sys.stderr)
    sys.exit(0)
