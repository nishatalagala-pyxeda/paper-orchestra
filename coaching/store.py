"""Local, transactional persistence; private reference content is excluded from assignment handouts."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from coaching.models import AssignmentDraft, FeedbackDraft, ReferenceDraft


class Conflict(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def ident():
    return uuid4().hex


class Store:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv('PAPER_ORCHESTRA_COACH_DB') or
                         Path(__file__).resolve().parents[1] / 'coaching_data' / 'workspace.sqlite3')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    state TEXT NOT NULL, updated TEXT NOT NULL);
            ''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_project(self, title, idea, methodology, results, goals, pages, template, guidelines, template_source=''):
        if not title.strip() or not idea.strip() or not methodology.strip():
            raise ValueError('A project title, research idea and methodology are required.')
        project = dict(id=ident(), title=title.strip(), idea=idea, methodology=methodology,
                       goals=goals, pages=pages, template=template, guidelines=guidelines,
                       template_source=template_source, created=now(), evidence=[], references=[],
                       versions=[], approved_reference=None, assignments=[])
        if results.strip():
            project['evidence'].append(dict(id='E1', label='Initial experiment log', body=results,
                                           kind='preliminary', created=now()))
        with self.connection() as db:
            db.execute('INSERT INTO projects VALUES (?, ?, ?, ?)',
                       (project['id'], project['title'], json.dumps(project), now()))
        return project['id']

    def list_projects(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute('SELECT id, title, updated FROM projects ORDER BY updated DESC')]

    def get(self, project_id):
        with self.connection() as db:
            row = db.execute('SELECT state FROM projects WHERE id=?', (project_id,)).fetchone()
        if not row:
            raise ValueError('Project not found.')
        return json.loads(row['state'])

    def _change(self, project_id, change):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT state FROM projects WHERE id=?', (project_id,)).fetchone()
            if not row:
                raise ValueError('Project not found.')
            state = json.loads(row[0])
            result = change(state)
            db.execute('UPDATE projects SET state=?, updated=? WHERE id=?', (json.dumps(state), now(), project_id))
            return result

    @staticmethod
    def _assignment(state, assignment_id):
        return next(a for a in state['assignments'] if a['id'] == assignment_id)

    def add_evidence(self, project_id, label, body, kind):
        if not label.strip() or not body.strip() or kind not in ('completed', 'preliminary', 'planned'):
            raise ValueError('Provide a label, experiment details, and an evidence status.')
        def change(s):
            item = dict(id=f"E{len(s['evidence']) + 1}", label=label, body=body, kind=kind, created=now())
            s['evidence'].append(item)
            return item['id']
        return self._change(project_id, change)

    @staticmethod
    def _validate_claims(state, draft):
        evidence = {e['id']: e for e in state['evidence']}
        for claim in draft['claims']:
            if any(e not in evidence for e in claim['evidence_ids']):
                raise ValueError('A claim refers to an unknown evidence ID.')
            if claim['status'] == 'verified' and (not claim['evidence_ids'] or
                    any(evidence[e]['kind'] != 'completed' for e in claim['evidence_ids'])):
                raise ValueError('Verified claims must cite completed evidence only.')

    def propose_reference(self, project_id, draft, evidence_count, base_reference):
        draft = ReferenceDraft.model_validate(draft).model_dump()
        def change(s):
            if len(s['evidence']) != evidence_count or s['approved_reference'] != base_reference:
                raise Conflict('The evidence or approved reference changed. Generate a fresh proposal.')
            self._validate_claims(s, draft)
            version = dict(id=ident(), number=len(s['versions']) + 1, created=now(), status='proposed',
                           evidence_count=evidence_count, base_reference=base_reference, **draft)
            s['versions'].append(version)
            return version['id']
        return self._change(project_id, change)

    def approve_reference(self, project_id, version_id, manuscript, claims):
        def change(s):
            version = next(v for v in s['versions'] if v['id'] == version_id)
            if version['status'] != 'proposed':
                raise Conflict('Only a proposed reference can be approved.')
            if version['base_reference'] != s['approved_reference'] or version['evidence_count'] != len(s['evidence']):
                raise Conflict('This proposal is out of date. Generate a fresh proposal using the current evidence.')
            edited = ReferenceDraft.model_validate({**version, 'manuscript': manuscript, 'claims': claims}).model_dump()
            self._validate_claims(s, edited)
            # Approval is a new immutable snapshot; the original AI proposal remains available.
            approved = dict(**edited, id=ident(), number=len(s['versions']) + 1,
                            created=now(), status='approved', evidence_count=len(s['evidence']),
                            base_reference=s['approved_reference'], proposal_id=version_id)
            s['versions'].append(approved)
            s['approved_reference'] = approved['id']
            version['status'] = 'reviewed'
            return approved['id']
        return self._change(project_id, change)

    def add_assignments(self, project_id, assignments, reference_id, evidence_count):
        assignments = [AssignmentDraft.model_validate(a).model_dump() for a in assignments]
        def change(s):
            if not reference_id or s['approved_reference'] != reference_id or len(s['evidence']) != evidence_count:
                raise Conflict('Approve the current reference before creating assignments. The project may have changed.')
            reference = next(v for v in s['versions'] if v['id'] == reference_id)
            if reference['evidence_count'] != len(s['evidence']):
                raise Conflict('Update and approve the reference using the latest evidence first.')
            ids = []
            for a in assignments:
                a = dict(**a, id=ident(), reference_id=reference_id, evidence_count=evidence_count,
                         status='draft', created=now(), submissions=[], feedback=[], release=None)
                s['assignments'].append(a)
                ids.append(a['id'])
            return ids
        return self._change(project_id, change)

    def release_assignment(self, project_id, assignment_id, edited):
        edited = AssignmentDraft.model_validate(edited).model_dump()
        def change(s):
            a = self._assignment(s, assignment_id)
            if a['status'] != 'draft':
                raise Conflict('This assignment has already been released.')
            if a['reference_id'] != s['approved_reference'] or a['evidence_count'] != len(s['evidence']):
                raise Conflict('The reference or evidence changed. Generate a current assignment proposal.')
            reference = next(v for v in s['versions'] if v['id'] == s['approved_reference'])
            if reference['evidence_count'] != len(s['evidence']):
                raise Conflict('Update and approve the reference using the latest evidence first.')
            a.update(edited)
            # Explicit allow-list: rationale and private reference are never released.
            a['release'] = {k: edited[k] for k in ('title', 'objective', 'prompt', 'deliverable', 'criteria',
                                                 'estimated_minutes', 'section')}
            a['released'] = now()
            a['status'] = 'ready'
        self._change(project_id, change)

    def assignment_handout(self, project_id, assignment_id):
        s = self.get(project_id)
        a = self._assignment(s, assignment_id)
        if not a['release']:
            raise ValueError('Approve the assignment before exporting its handout.')
        return dict(a['release'])

    def record_submission(self, project_id, assignment_id, text, reflection=''):
        if not text.strip():
            raise ValueError('Paste or upload the student’s response before recording it.')
        def change(s):
            a = self._assignment(s, assignment_id)
            if not a['release'] or a['status'] not in ('ready', 'revision_requested'):
                raise Conflict('This assignment is not accepting a submission. Refresh the page.')
            sub = dict(id=ident(), text=text, reflection=reflection, created=now())
            a['submissions'].append(sub)
            a['status'] = 'submitted'
            return sub['id']
        return self._change(project_id, change)

    def propose_feedback(self, project_id, assignment_id, submission_id, draft):
        draft = FeedbackDraft.model_validate(draft).model_dump()
        def change(s):
            a = self._assignment(s, assignment_id)
            sub = a['submissions'][-1]
            if sub['id'] != submission_id:
                raise Conflict('The submission changed. Review the latest submission.')
            if any(p['quote'] not in sub['text'] for p in draft['points']):
                raise ValueError('Feedback includes a quote that is not in the student submission.')
            a['feedback'].append(dict(id=ident(), submission_id=submission_id, status='proposed',
                                      created=now(), **draft))
        self._change(project_id, change)

    def release_feedback(self, project_id, assignment_id, submission_id, message, decision):
        if not message.strip() or decision not in ('complete', 'revision_requested'):
            raise ValueError('Provide feedback and a decision.')
        def change(s):
            a = self._assignment(s, assignment_id)
            if not a['submissions'] or a['submissions'][-1]['id'] != submission_id:
                raise Conflict('The submission changed. Review the latest version.')
            if a['status'] != 'submitted':
                raise Conflict('This submission has already been reviewed.')
            a['feedback'].append(dict(id=ident(), submission_id=submission_id, message=message,
                                      decision=decision, status='released', created=now()))
            a['status'] = decision
        self._change(project_id, change)

    def add_sources(self, project_id, sources):
        def change(s):
            for source in sources:
                s['references'].append(dict(**source, id=ident(), status='suggested', created=now()))
        self._change(project_id, change)

    def release_source(self, project_id, source_id, title, url, citation, question, checked):
        from urllib.parse import urlparse
        if not checked or not title.strip() or not question.strip():
            raise ValueError('Verify the source and provide a title and reading question.')
        if urlparse(url).scheme != 'https' or not urlparse(url).netloc:
            raise ValueError('Use a complete HTTPS source link.')
        def change(s):
            r = next(r for r in s['references'] if r['id'] == source_id)
            r.update(title=title, url=url, citation=citation, reading_question=question,
                     status='approved', teacher_checked=True)
        self._change(project_id, change)
