"""Regression checks for local startup; no model calls or secrets required."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from utils.runtime_config import ROOT, setup_local_tools


class StartupTests(unittest.TestCase):
    def test_pipeline_import_without_provider_credentials(self):
        # dotenv is disabled so a developer's local credentials cannot mask this bug.
        env = {k: v for k, v in os.environ.items() if k not in (
            'OPENAI_API_KEY', 'GEMINI_API_KEY', 'VERTEX_AI_PROJECT', 'VERTEX_AI_LOCATION')}
        env['PYTHON_DOTENV_DISABLED'] = '1'
        result = subprocess.run([sys.executable, '-c',
            'from utils.runtime_config import setup_local_tools; setup_local_tools(); '
            'from methods import paper_writer, paper_writer_with_plotting'],
            cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cli_propagates_pipeline_failure(self):
        import types
        import paper_writing_cli
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / 'raw'
            raw.mkdir()
            (raw / 'idea_sparse.md').write_text('Test idea')
            (raw / 'experimental_log.md').write_text('Test log')
            argv = ['paper_writing_cli.py', '--raw_materials_dir', str(raw),
                    '--latex_template_dir', str(ROOT / 'templates/cvpr2025'),
                    '--output_dir', str(Path(tmp) / 'out')]
            fake = types.ModuleType('methods.paper_writer')
            fake.write_single_paper = lambda **kwargs: False
            with patch.object(sys, 'argv', argv), \
                 patch('utils.runtime_config.generation_errors', return_value=[]), \
                 patch.dict(sys.modules, {'methods.paper_writer': fake}):
                self.assertEqual(paper_writing_cli.main(), 1)

    def test_demo_and_example_load_without_keys(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(ROOT / 'frontend/app.py'), default_timeout=45).run()
        self.assertFalse(app.exception)
        app.sidebar.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.session_state['idea_text_main'])
        self.assertTrue(app.session_state['log_text_main'])
        self.assertTrue(app.session_state['figures'])
        # Missing credentials must leave the editable inputs visible.
        with patch('utils.runtime_config.generation_errors', return_value=['Missing Gemini key']):
            next(b for b in app.button if 'Begin Writing' in b.label).click().run()
        self.assertFalse(app.session_state['running'])
        self.assertFalse(app.session_state['hide_inputs'])
        self.assertTrue(app.error)


if __name__ == '__main__':
    setup_local_tools()
    unittest.main()
