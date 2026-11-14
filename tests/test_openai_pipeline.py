"""Exercise actual agent code with fake API responses and no Gemini credentials."""
import base64
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from google.genai import types
from PIL import Image
from utils.runtime_config import ROOT, generation_errors, setup_local_tools
from utils.llm_backend_utils import call_llm_with_contents

MODEL = 'gpt-6-astra'
LATEX = r'\documentclass{article}\begin{document}' + ('A test paper about measured results and reproducible experiments. ' * 8) + r'\end{document}'


class OpenAIPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.client = Mock()
        self.client.responses.create.return_value = SimpleNamespace(status='completed', output_text='{"ok": true}')
        self.key_patch = patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only', 'GEMINI_API_KEY': '',
                                               'VERTEX_AI_PROJECT': '', 'VERTEX_AI_LOCATION': ''})
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.client_patch = patch('utils.openai_utils.get_openai_client', return_value=self.client)
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.gemini = patch('utils.gemini_utils.get_genai_client', side_effect=AssertionError('Gemini must not be called'))
        self.gemini.start()
        self.addCleanup(self.gemini.stop)
        self.idea = self.work / 'idea.md'
        self.log = self.work / 'log.md'
        self.idea.write_text('A small test idea.')
        self.log.write_text('A small test measurement.')

    def reply(self, text):
        self.client.responses.create.return_value = SimpleNamespace(status='completed', output_text=text)

    def test_provider_checks_only_require_selected_keys(self):
        self.assertFalse(generation_errors([MODEL]))
        self.assertTrue(generation_errors(['gemini-3.1-pro-preview']))

    def test_real_sdk_serializes_responses_request(self):
        import httpx2
        from openai import OpenAI
        requests = []
        def handle(request):
            requests.append(json.loads(request.content))
            self.assertEqual(request.url.path, '/v1/responses')
            return httpx2.Response(200, json={
                'id': 'resp_test', 'object': 'response', 'created_at': 0,
                'status': 'completed', 'model': MODEL,
                'output': [{'id': 'msg_test', 'type': 'message', 'role': 'assistant',
                            'status': 'completed', 'content': [{'type': 'output_text',
                            'text': '{"ok":true}', 'annotations': []}]}]})
        with httpx2.Client(transport=httpx2.MockTransport(handle)) as http:
            with OpenAI(api_key='test-only', http_client=http) as client:
                with patch('utils.openai_utils.get_openai_client', return_value=client):
                    result = call_llm_with_contents(['Search for test papers'], MODEL,
                        generation_configs={'tools': [types.Tool(google_search=types.GoogleSearch())]})
        self.assertEqual(result['parsed_response'], {'ok': True})
        self.assertEqual(requests[0]['tools'], [{'type': 'web_search'}])

    def test_explicit_gemini_selection_keeps_original_adapter(self):
        with patch('utils.llm_backend_utils.call_gemini_with_contents', return_value={'parsed_response': {}}) as call:
            call_llm_with_contents(['test'], 'gemini-3.1-pro-preview',
                                   generation_configs={'temperature': 0.4})
        self.assertEqual(call.call_args.kwargs['generation_configs']['temperature'], 0.4)
        self.client.responses.create.assert_not_called()

    def test_outline_and_grounded_literature_discovery(self):
        from methods.agents.outline_agent import OutlineAgent
        from methods.agents.literature_review_agent import HybridLiteratureAgent
        args = dict(idea_file=str(self.idea), experimental_log_file=str(self.log),
                    latex_template_file=str(ROOT / 'templates/cvpr2025/template.tex'),
                    conference_guidelines_file=str(ROOT / 'templates/cvpr2025/guidelines.md'))
        self.assertEqual(OutlineAgent(model_name=MODEL).run(**args), {'ok': True})
        agent = HybridLiteratureAgent(str(self.idea), str(self.log), args['latex_template_file'],
                                     args['conference_guidelines_file'], str(self.work / 'literature'), model_name=MODEL)
        self.reply('{"candidates": [{"title": "Test paper", "year": 2020}]}')
        papers = agent._discover_candidates({'focus': 'measured results', 'context': 'test', 'search_type': 'targeted'}, {}, '2026-11')
        self.assertEqual(papers[0]['title'], 'Test paper')
        request = self.client.responses.create.call_args.kwargs
        self.assertEqual(request['tools'], [{'type': 'web_search'}])
        self.assertEqual(request['tool_choice'], 'required')
        self.assertEqual(request['model'], MODEL)
        self.assertNotIn('temperature', request)
        self.reply('```latex\nIntroduction.\n```')
        self.assertEqual(agent._synthesize_content({}, [], '2026-11'), 'Introduction.')

    def test_native_pdf_and_image_inputs_and_parsers(self):
        result = call_llm_with_contents([
            types.Part.from_bytes(data=b'%PDF-test', mime_type='application/pdf'),
            types.Part.from_bytes(data=b'image', mime_type='image/png'), 'Review this'], MODEL,
            generation_configs={'system_instruction': 'Be precise', 'temperature': 0.7})
        self.assertEqual(result['parsed_response'], {'ok': True})
        request = self.client.responses.create.call_args.kwargs
        pdf, image, text = request['input'][0]['content']
        self.assertEqual(base64.b64decode(pdf['file_data'].split(',')[1]), b'%PDF-test')
        self.assertEqual(image['type'], 'input_image')
        self.assertEqual(request['instructions'], 'Be precise')
        self.assertFalse(request['store'])

    def test_incomplete_and_invalid_outputs_fail(self):
        self.client.responses.create.return_value = SimpleNamespace(status='incomplete', output_text='partial')
        with self.assertRaisesRegex(RuntimeError, 'did not complete'):
            call_llm_with_contents(['test'], MODEL)
        self.reply('this is not json')
        with self.assertRaisesRegex(ValueError, 'could not be parsed'):
            call_llm_with_contents(['test'], MODEL)

    def test_plot_and_diagram_render_without_gemini(self):
        from utils.paper_banana_utils import generate_figure_visuals
        self.reply('```python\nimport matplotlib.pyplot as plt\nplt.figure(figsize=(2, 1))\nplt.plot([0, 1], [0, 1])\n```')
        for task in ('plot', 'diagram'):
            image = generate_figure_visuals(task, 'Test figure', model_name=MODEL)
            self.assertIsNotNone(image)
            Image.open(io.BytesIO(base64.b64decode(image))).verify()

    def test_section_writing_with_figure(self):
        from methods.agents.section_writing_agent import SectionWritingAgent
        outline = self.work / 'outline.json'
        outline.write_text('{}')
        citations = self.work / 'citations.json'
        citations.write_text('{}')
        image = self.work / 'figure.png'
        Image.new('RGB', (10, 10), 'white').save(image)
        figures = self.work / 'info.json'
        figures.write_text(json.dumps([{'name': 'figure.png', 'caption': 'Test figure'}]))
        self.reply('```latex\n' + LATEX + '\n```')
        agent = SectionWritingAgent(str(outline), str(self.idea), str(self.idea),
                                    str(self.log), str(citations), str(figures),
                                    str(self.idea), model_name=MODEL)
        output = self.work / 'sections.tex'
        agent.run(str(output))
        self.assertIn('documentclass', output.read_text())
        content = self.client.responses.create.call_args.kwargs['input'][0]['content']
        self.assertTrue(any(part['type'] == 'input_image' for part in content))

    def test_refinement_and_visual_review_with_real_latex(self):
        from methods.agents.content_refinement_agent import ContentRefinementAgent
        citation_map = self.work / 'citations.json'
        citation_map.write_text('{}')
        draft = self.work / 'draft.tex'
        draft.write_text(LATEX)
        agent = ContentRefinementAgent(str(self.log), str(citation_map), str(self.idea),
                                       model_name=MODEL, max_reflections=1, work_dir=str(self.work))
        def response(**request):
            content = request['input'][0]['content']
            text = '\n'.join(p.get('text', '') for p in content)
            if 'REFLECTION ITERATION' in text:
                output = '```json\n{"changes": "test"}\n```\n```latex\n' + LATEX + '\n```'
            elif 'Analyze the provided page images' in text:
                output = '{"figure_and_tables": {}, "other_issues": []}'
            else:
                output = '{"Overall": 7, "Confidence": 3, "Decision": "Accept"}'
            return SimpleNamespace(status='completed', output_text=output)
        self.client.responses.create.side_effect = response
        output = agent.run(str(draft))
        self.assertTrue(Path(output).is_file(), output)
        self.assertEqual(agent.current_score, 7)
        self.assertTrue((self.work / "peer_reviews/review_v0.json").is_file())
        requests = [call.kwargs for call in self.client.responses.create.call_args_list]
        kinds = {part['type'] for r in requests for part in r['input'][0]['content']}
        self.assertIn('input_file', kinds)
        self.assertIn('input_image', kinds)
        self.assertTrue(all(r['model'] == MODEL for r in requests))


if __name__ == '__main__':
    setup_local_tools()
    unittest.main()
