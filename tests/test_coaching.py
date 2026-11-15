"""Teacher workflow invariants; all model responses are simulated."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from coaching.service import Coach
from coaching.store import Store, Conflict

TASK = dict(title='Explain your controls', objective='Explain how the comparison is fair.',
            prompt='Describe the controls in your experiment and justify each one.',
            deliverable='A 150-word explanation written by the student.',
            criteria=['Identify the controlled variables.', 'Explain why each control matters.'],
            estimated_minutes=30, section='Methods', teacher_rationale='PRIVATE teaching rationale')
DRAFT = dict(manuscript='# Private teacher reference\n\nPRIVATE benchmark prose. Results are still preliminary.',
             claims=[dict(claim='The result is preliminary.', status='preliminary', evidence_ids=['E1'], explanation='Initial run only.')],
             change_summary=['Initial draft.'], assignment_impacts=['Assign a methods explanation.'])
FEEDBACK = dict(strengths=['The control is identified.'], points=[dict(quote='We kept the dataset fixed.',
                observation='The reason is missing.', question='Why must that stay fixed?')],
                next_task='Explain why fixing the dataset helps a fair comparison.', teacher_notes='PRIVATE reviewer notes')


class CoachingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'workspace.db'
        self.store = Store(self.path)
        self.pid = self.store.create_project('Research', 'Test idea', 'Method with controls', 'First run: 0.7 accuracy.',
            'Explain evidence', 8, 'General', 'Keep claims calibrated.')

    def approve(self, draft=None):
        p = self.store.get(self.pid)
        draft = copy.deepcopy(draft or DRAFT)
        vid = self.store.propose_reference(self.pid, draft, len(p['evidence']), p['approved_reference'])
        return self.store.approve_reference(self.pid, vid, draft['manuscript'], draft['claims'])

    def task(self):
        ref = self.approve()
        aid = self.store.add_assignments(self.pid, [TASK], ref, 1)[0]
        self.store.release_assignment(self.pid, aid, TASK)
        return aid

    def test_proposal_is_not_approval_and_approved_edit_is_new_snapshot(self):
        vid = self.store.propose_reference(self.pid, DRAFT, 1, None)
        self.assertIsNone(self.store.get(self.pid)['approved_reference'])
        edited = DRAFT['manuscript'] + '\nTeacher correction.'
        approved = self.store.approve_reference(self.pid, vid, edited, DRAFT['claims'])
        p = self.store.get(self.pid)
        self.assertEqual(len(p['versions']), 2)
        self.assertEqual(p['versions'][0]['manuscript'], DRAFT['manuscript'])
        self.assertEqual(p['approved_reference'], approved)
        self.assertEqual(p['versions'][1]['manuscript'], edited)
        self.assertEqual(Store(self.path).get(self.pid), p)

    def test_evidence_update_preserves_reference_assignments_and_submissions(self):
        aid = self.task()
        sid = self.store.record_submission(self.pid, aid, 'We kept the dataset fixed.')
        before = self.store.get(self.pid)
        self.store.add_evidence(self.pid, 'Correction to E1', 'The baseline was measured incorrectly.', 'completed')
        p = self.store.get(self.pid)
        self.assertEqual(p['assignments'], before['assignments'])
        self.assertEqual(p['versions'], before['versions'])
        with self.assertRaises(Conflict):
            self.store.add_assignments(self.pid, [TASK], p['approved_reference'], 2)
        updated = copy.deepcopy(DRAFT)
        updated['claims'] = [dict(claim='Earlier finding was contradicted.', status='contradicted', evidence_ids=['E1', 'E2'], explanation='Correction changes interpretation.')]
        self.approve(updated)
        self.assertEqual(self.store.get(self.pid)['assignments'][0]['submissions'][0]['id'], sid)
        self.assertEqual(self.store.get(self.pid)['assignments'][0]['status'], 'submitted')

    def test_stale_reference_proposals_cannot_replace_current_work(self):
        vid = self.store.propose_reference(self.pid, DRAFT, 1, None)
        self.store.add_evidence(self.pid, 'Another run', 'Measurement: 0.6.', 'completed')
        with self.assertRaises(Conflict):
            self.store.approve_reference(self.pid, vid, DRAFT['manuscript'], DRAFT['claims'])
        with self.assertRaises(Conflict):
            self.store.propose_reference(self.pid, DRAFT, 1, None)
        self.assertIsNone(self.store.get(self.pid)['approved_reference'])

    def test_verified_claims_need_completed_known_evidence(self):
        draft = copy.deepcopy(DRAFT)
        draft['claims'][0]['status'] = 'verified'
        with self.assertRaisesRegex(ValueError, 'completed evidence'):
            self.store.propose_reference(self.pid, draft, 1, None)
        draft['claims'][0]['evidence_ids'] = ['made-up']
        with self.assertRaisesRegex(ValueError, 'unknown evidence'):
            self.store.propose_reference(self.pid, draft, 1, None)
        self.assertFalse(self.store.get(self.pid)['versions'])

    def test_handout_excludes_private_reference_and_teaching_notes(self):
        aid = self.task()
        handout = json.dumps(self.store.assignment_handout(self.pid, aid))
        self.assertNotIn('PRIVATE', handout)
        self.assertNotIn('reference_id', handout)
        self.assertNotIn('teacher_rationale', handout)
        self.assertIn(TASK['prompt'], handout)

    def test_feedback_has_exact_quotes_and_revisions_are_append_only(self):
        aid = self.task()
        sid = self.store.record_submission(self.pid, aid, 'We kept the dataset fixed.')
        bad = copy.deepcopy(FEEDBACK)
        bad['points'][0]['quote'] = 'Student never said this.'
        with self.assertRaisesRegex(ValueError, 'not in the student'):
            self.store.propose_feedback(self.pid, aid, sid, bad)
        self.store.propose_feedback(self.pid, aid, sid, FEEDBACK)
        a = self.store.get(self.pid)['assignments'][0]
        self.assertEqual(a['status'], 'submitted')
        self.assertEqual(a['feedback'][0]['status'], 'proposed')
        self.store.release_feedback(self.pid, aid, sid, 'Explain why the dataset is fixed.', 'revision_requested')
        sid2 = self.store.record_submission(self.pid, aid, 'We kept the dataset fixed to isolate the method.')
        with self.assertRaises(Conflict):
            self.store.release_feedback(self.pid, aid, sid, 'Stale feedback', 'complete')
        self.store.release_feedback(self.pid, aid, sid2, 'The reasoning is now clear.', 'complete')
        a = self.store.get(self.pid)['assignments'][0]
        self.assertEqual(len(a['submissions']), 2)
        self.assertEqual(a['submissions'][0]['text'], 'We kept the dataset fixed.')
        self.assertEqual(a['status'], 'complete')

    def test_sources_require_teacher_verification_before_handout(self):
        self.store.add_sources(self.pid, [dict(title='Source', url='https://example.org/paper', reading_question='What does it test?',
            citation='Author, year.', reason='Relevant', verification='Not checked')])
        source = self.store.get(self.pid)['references'][0]
        with self.assertRaises(ValueError):
            self.store.release_source(self.pid, source['id'], source['title'], source['url'], source['citation'], source['reading_question'], False)
        self.store.release_source(self.pid, source['id'], source['title'], source['url'], source['citation'], source['reading_question'], True)
        self.assertEqual(self.store.get(self.pid)['references'][0]['status'], 'approved')

    @patch('coaching.service.call_llm_with_text_prompt')
    def test_ai_generates_proposals_only_and_feedback_is_private(self, model):
        coach = Coach(self.store)
        model.return_value = {'parsed_response': DRAFT}
        coach.propose_reference(self.pid)
        p = self.store.get(self.pid)
        self.assertIsNone(p['approved_reference'])
        self.store.approve_reference(self.pid, p['versions'][0]['id'], DRAFT['manuscript'], DRAFT['claims'])
        model.return_value = {'parsed_response': {'assignments': [TASK]}}
        coach.propose_assignments(self.pid, 'Teach experimental controls.')
        a = self.store.get(self.pid)['assignments'][0]
        self.assertEqual(a['status'], 'draft')
        self.assertIsNone(a['release'])
        self.store.release_assignment(self.pid, a['id'], TASK)
        self.store.record_submission(self.pid, a['id'], 'We kept the dataset fixed.')
        model.return_value = {'parsed_response': FEEDBACK}
        coach.propose_feedback(self.pid, a['id'])
        a = self.store.get(self.pid)['assignments'][0]
        self.assertEqual(a['status'], 'submitted')
        self.assertEqual(a['feedback'][0]['status'], 'proposed')
        prompt = model.call_args.args[0]
        self.assertIn('Do not rewrite passages', prompt)
