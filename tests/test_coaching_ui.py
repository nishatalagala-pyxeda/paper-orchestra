"""Exercise the teacher-only UI against an isolated local database."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from coaching.store import Store
from test_coaching import TASK, DRAFT

ROOT = Path(__file__).resolve().parents[1]


def labeled(elements, label):
    return next(e for e in elements if e.label == label)


class TeacherUITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'coach.sqlite3'
        self.env = patch.dict(os.environ, {'PAPER_ORCHESTRA_COACH_DB': str(self.path)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.store = Store(self.path)

    def test_project_creation_is_teacher_only_and_persists(self):
        app = AppTest.from_file(str(ROOT / 'frontend/teacher_app.py'), default_timeout=45).run()
        self.assertFalse(app.exception)
        self.assertFalse(any('login' in t.label.lower() or 'password' in t.label.lower() for t in app.text_input))
        labeled(app.text_input, 'Project title').input('Test coaching project')
        labeled(app.text_area, 'Student’s research idea').input('Investigate measured performance.')
        labeled(app.text_area, 'Experimental methodology').input('Compare against a fixed baseline.')
        labeled(app.button, 'Create teaching project').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.store.list_projects()[0]['title'], 'Test coaching project')
        self.assertTrue(any(t.label == 'Reference draft' for t in app.tabs))
        self.assertTrue(any('No reference yet' in i.value for i in app.info))

    def test_reference_approval_and_recording_student_work(self):
        pid = self.store.create_project('Test', 'Idea', 'Method', 'Preliminary results.', 'Learn', 8, 'General', '')
        vid = self.store.propose_reference(pid, DRAFT, 1, None)
        app = AppTest.from_file(str(ROOT / 'frontend/teacher_app.py'), default_timeout=45).run()
        self.assertFalse(app.exception)
        labeled(app.checkbox, 'I reviewed the manuscript, evidence labels and limitations.').check()
        labeled(app.button, 'Approve reference snapshot').click().run()
        self.assertFalse(app.exception)
        p = self.store.get(pid)
        self.assertIsNotNone(p['approved_reference'])
        self.assertEqual(len(p['versions']), 2)
        aid = self.store.add_assignments(pid, [TASK], p['approved_reference'], 1)[0]
        self.store.release_assignment(pid, aid, TASK)
        app.run()
        self.assertFalse(app.exception)
        labeled(app.text_area, 'Paste the student’s own response').input('We kept the dataset fixed.')
        labeled(app.button, 'Record student submission').click().run()
        self.assertFalse(app.exception)
        a = self.store.get(pid)['assignments'][0]
        self.assertEqual(a['status'], 'submitted')
        labeled(app.text_area, 'Your feedback to give the student').input('Explain why the fixed dataset matters.')
        labeled(app.button, 'Save reviewed feedback').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(self.store.get(pid)['assignments'][0]['status'], 'revision_requested')
        self.assertEqual(self.store.get(pid)['versions'][0]['manuscript'], DRAFT['manuscript'])

    def test_original_writer_remains_available(self):
        app = AppTest.from_file(str(ROOT / 'frontend/teacher_app.py'), default_timeout=45)
        app.query_params['mode'] = 'writer'
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any(t.value == '🎻 Paper Orchestra Demo' for t in app.title))

    def test_missing_key_preserves_project_and_shows_actionable_message(self):
        self.store.create_project('Test', 'Idea', 'Method', '', 'Learn', 8, 'General', '')
        app = AppTest.from_file(str(ROOT / 'frontend/teacher_app.py'), default_timeout=45).run()
        with patch.dict(os.environ, {'OPENAI_API_KEY': '', 'GEMINI_API_KEY': '', 'VERTEX_AI_PROJECT': '', 'VERTEX_AI_LOCATION': ''}):
            labeled(app.button, 'Propose reference draft / update').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('API key' in e.value for e in app.error))
        self.assertFalse(self.store.get(self.store.list_projects()[0]['id'])['versions'])
