"""Teacher-only research-writing workspace. No student accounts or portal."""
import difflib
import json
import os
from pathlib import Path
import runpy
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Keep the original generator available without duplicating its UI or pipeline.
if st.query_params.get('mode') == 'writer':
    runpy.run_path(str(ROOT / 'frontend' / 'app.py'), run_name='__main__')
    st.stop()

from coaching.service import Coach
from coaching.store import Store
from utils.model_config import DEFAULT_MODEL, is_openai_model
from utils.runtime_config import setup_local_tools

setup_local_tools()
st.set_page_config(page_title='Paper Orchestra · Teacher Workspace', page_icon='🎻', layout='wide')
store = Store()
coach = Coach(store)

st.markdown('''<style>
.block-container {max-width: 1200px; padding-top: 2rem;}
[data-testid="stSidebar"] {background: #f1f5f9;}
[data-testid="stMetric"] {border: 1px solid #e2e8f0; border-radius: 12px; padding: 14px;}
</style>''', unsafe_allow_html=True)


def credential_ready():
    if is_openai_model(DEFAULT_MODEL):
        return bool(os.getenv('OPENAI_API_KEY'))
    return bool(os.getenv('GEMINI_API_KEY') or (os.getenv('VERTEX_AI_PROJECT') and os.getenv('VERTEX_AI_LOCATION')))


def action(label, fn, ai=False):
    try:
        if ai and not credential_ready():
            st.error('Add your model API key to .env and restart the app to use AI suggestions. You can use the manual workflow now.')
            return
        with st.spinner(label):
            fn()
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f'This action could not finish ({type(exc).__name__}). Your saved work is preserved. Check your API access or server logs and try again.')


def uploaded_text(upload):
    if upload is None:
        return ''
    try:
        return upload.getvalue().decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ValueError('Please upload a UTF-8 text or Markdown file.')


def handout_markdown(task):
    criteria = '\n'.join('- ' + c for c in task['criteria'])
    return (f"# {task['title']}\n\n**Learning goal:** {task['objective']}\n\n"
            f"**Time guide:** {task['estimated_minutes']} minutes\n\n"
            f"## Your task\n{task['prompt']}\n\n## Submit\n{task['deliverable']}\n\n"
            f"## Completion criteria\n{criteria}\n")


def feedback_markdown(draft):
    parts = ['What is working:', *['- ' + x for x in draft['strengths']], '', 'Questions to address:']
    for point in draft['points']:
        parts.extend([f"\n> {point['quote']}", point['observation'], point['question']])
    if draft['next_task']:
        parts.extend(['', 'Next step:', draft['next_task']])
    return '\n\n'.join(parts)


def create_project():
    st.header('Start a teaching project')
    st.write('Bring the student’s idea and methodology. Results can be incomplete. The private reference will guide your teaching, while the student writes every part of their own paper.')
    if st.button('Load sample materials', key='sample-materials'):
        sample = json.loads((ROOT / 'frontend/examples/cvpr_example.json').read_text())
        st.session_state['new_title'] = 'Sample · Audio-visual segmentation'
        st.session_state['new_idea'] = sample['idea']
        st.session_state['new_methodology'] = 'See the proposed methodology in the idea. Review and adapt these sample materials before using them.'
        st.session_state['new_results'] = sample['log']
        st.rerun()
    with st.form('new-project'):
        title = st.text_input('Project title', key='new_title')
        col1, col2 = st.columns(2)
        with col1:
            idea = st.text_area('Student’s research idea', height=190, key='new_idea')
            idea_file = st.file_uploader('Or upload the idea', type=['md', 'txt'], key='new-idea-file')
            methodology = st.text_area('Experimental methodology', height=160, key='new_methodology')
        with col2:
            results = st.text_area('Current results / experiment log (optional)', height=190, key='new_results')
            st.caption('Initial results are recorded as preliminary. Add completed evidence entries after checking them.')
            result_file = st.file_uploader('Or upload the experiment log', type=['md', 'txt'], key='new-log-file')
            goals = st.text_area('Learning goals and student experience', value='Explain a research question, document reproducible methods, interpret evidence carefully, and write related work independently.', height=160)
        c1, c2 = st.columns(2)
        pages = c1.number_input('Target main-text pages (planning guide)', min_value=1, max_value=100, value=8)
        template = c2.selectbox('Writing / formatting guide', ['General research paper', 'cvpr2025', 'iclr2025', 'Custom LaTeX'])
        latex = st.file_uploader('Custom main .tex source (optional)', type=['tex'], key='new-tex')
        guidelines = st.text_area('Additional instructions or formatting guidelines', placeholder='For example: 8 pages excluding references. Use a neutral scientific voice.')
        st.caption('The reference is edited and exported as Markdown. LaTeX source and conference guidelines guide its structure; page count is approximate. The separate paper generator remains available for PDF production.')
        if st.form_submit_button('Create teaching project', type='primary'):
            def create():
                rules = guidelines
                source = uploaded_text(latex)
                if template in ('cvpr2025', 'iclr2025'):
                    rules = (ROOT / 'templates' / template / 'guidelines.md').read_text() + '\n' + rules
                    source = source or (ROOT / 'templates' / template / 'template.tex').read_text()
                if template == 'Custom LaTeX' and not source:
                    raise ValueError('Upload the custom .tex source or select another guide.')
                pid = store.create_project(title, uploaded_text(idea_file) or idea, methodology,
                                           uploaded_text(result_file) or results, goals, pages,
                                           template, rules, source)
                st.session_state['coach_pending_project'] = pid
            action('Saving your project…', create)


def overview(project):
    reference = coach.reference(project)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric('Evidence entries', len(project['evidence']))
    c2.metric('Approved reference', f"v{reference['number']}" if reference else 'Not yet')
    c3.metric('Ready / in revision', sum(a['status'] in ('ready', 'revision_requested') for a in project['assignments']))
    c4.metric('Submissions to review', sum(a['status'] == 'submitted' for a in project['assignments']))
    st.subheader('Your teaching flow')
    st.write('Record evidence → propose a reference → review and approve → propose micro-assignments → edit and export handouts → record student work → give feedback and a next task.')
    if not reference:
        st.info('Next: open Reference draft to generate a private draft or import one you have written.')
    elif reference['evidence_count'] != len(project['evidence']):
        st.warning('New evidence arrived after the approved reference. Propose and review an update before creating new assignments. Existing student work is preserved.')
    elif not project['assignments']:
        st.info('Next: open Assignments to plan small tasks from your approved reference.')
    st.markdown('**Student authorship:** reference wording is for you. Handouts contain tasks and criteria; the student supplies the reasoning, prose, figures and related-work synthesis.')
    with st.expander('Project brief'):
        st.markdown(project['idea'])
        st.markdown('**Methodology**\n\n' + project['methodology'])
        st.markdown('**Learning goals**\n\n' + project['goals'])
    st.download_button('Download private project backup', json.dumps(project, indent=2),
                       file_name=f"teacher-project-{project['id'][:8]}.json", mime='application/json')
    st.caption('Projects are saved on this computer. This is a teacher-only local workspace; no student accounts, portal, or automatic messages are created.')


def evidence_tab(project):
    st.subheader('Results and experiment history')
    st.write('Add new results as separate entries. If a previous result was wrong, add a correction naming the earlier evidence ID so the history stays traceable.')
    with st.form('new-evidence'):
        label = st.text_input('Result or experiment label', placeholder='Ablation run 2, corrected baseline, or planned robustness test')
        kind = st.selectbox('Evidence status', ['preliminary', 'completed', 'planned'])
        body = st.text_area('Details, measurements, units, setup and caveats', height=160)
        file = st.file_uploader('Or upload a result log', type=['md', 'txt'], key='evidence-upload')
        if st.form_submit_button('Save evidence entry', type='primary'):
            action('Saving evidence…', lambda: store.add_evidence(project['id'], label, uploaded_text(file) or body, kind))
    for item in reversed(project['evidence']):
        with st.expander(f"{item['id']} · {item['label']} · {item['kind']}"):
            st.caption(item['created'])
            st.markdown(item['body'])


def reference_tab(project):
    st.subheader('Private teacher reference')
    st.write('Use this as a provisional teaching benchmark. Review its science and evidence labels before approving. A student may reach a different, valid interpretation.')
    if st.button('Propose reference draft / update', type='primary'):
        action('Preparing a private reference proposal…', lambda: coach.propose_reference(project['id']), ai=True)
    with st.expander('Import a reference you wrote (no API needed)'):
        with st.form('manual-reference'):
            text = st.text_area('Reference manuscript', height=180, key='manual-reference-text')
            file = st.file_uploader('Or upload a reference draft', type=['md', 'txt'], key='manual-reference-file')
            if st.form_submit_button('Save as a proposal'):
                def save_import():
                    draft = dict(manuscript=uploaded_text(file) or text, claims=[],
                                 change_summary=['Teacher supplied a reference draft.'], assignment_impacts=[])
                    store.propose_reference(project['id'], draft, len(project['evidence']), project['approved_reference'])
                action('Saving a reference proposal…', save_import)
    if not project['versions']:
        st.info('No reference yet. Generate a proposal or import your own draft above.')
        return
    versions = {v['id']: v for v in project['versions']}
    chosen = st.selectbox('Reference version', list(reversed(versions)),
                          format_func=lambda v: f"v{versions[v]['number']} · {versions[v]['status']} · {versions[v]['created']}")
    v = versions[chosen]
    st.caption(f"Based on {v['evidence_count']} evidence entries. Earlier snapshots remain available.")
    for text in v['change_summary']:
        st.markdown('- ' + text)
    if v['assignment_impacts']:
        st.markdown('**Suggested assignment follow-ups**')
        for text in v['assignment_impacts']:
            st.markdown('- ' + text)
        st.caption('These are suggestions only. Existing handouts, submissions and feedback have not been changed.')
    if v['base_reference'] in versions:
        with st.expander('Changes from the previous approved reference'):
            diff = '\n'.join(difflib.unified_diff(versions[v['base_reference']]['manuscript'].splitlines(),
                                                  v['manuscript'].splitlines(), fromfile='Previous approved', tofile='This version', lineterm=''))
            st.code(diff or 'No manuscript text changes.', language='diff')
    with st.expander('Read the manuscript', expanded=True):
        st.markdown(v['manuscript'])
    st.download_button('Download this private reference', v['manuscript'], file_name=f"private-reference-v{v['number']}.md", mime='text/markdown')
    if v['status'] == 'proposed':
        stale = v['evidence_count'] != len(project['evidence']) or v['base_reference'] != project['approved_reference']
        if stale:
            st.warning('This proposal predates current evidence or another approval. Generate a fresh proposal; it cannot replace the current reference.')
        with st.form('approve-reference-' + chosen):
            manuscript = st.text_area('Review and edit the private manuscript', value=v['manuscript'], height=300)
            st.markdown('**Review the claim / evidence ledger**')
            st.caption('Use evidence IDs such as E1. “Verified” requires completed evidence. Separate multiple IDs with commas.')
            rows = [{**c, 'evidence_ids': ', '.join(c['evidence_ids'])} for c in v['claims']]
            frame = pd.DataFrame(rows, columns=['claim', 'status', 'evidence_ids', 'explanation'])
            ledger = st.data_editor(frame, num_rows='dynamic', hide_index=True,
                column_config={'status': st.column_config.SelectboxColumn(options=['verified', 'preliminary', 'unanswered', 'contradicted'])},
                key='ledger-' + chosen)
            checked = st.checkbox('I reviewed the manuscript, evidence labels and limitations.')
            if st.form_submit_button('Approve reference snapshot', type='primary', disabled=stale):
                def approve():
                    if not checked:
                        raise ValueError('Review the reference and confirm before approving it.')
                    claims = []
                    for c in ledger.fillna('').to_dict('records'):
                        if not c['claim'].strip():
                            continue
                        claims.append({**c, 'evidence_ids': [e.strip() for e in c['evidence_ids'].split(',') if e.strip()]})
                    store.approve_reference(project['id'], chosen, manuscript, claims)
                action('Saving an approved reference snapshot…', approve)
    elif v['claims']:
        st.dataframe([{**c, 'evidence_ids': ', '.join(c['evidence_ids'])} for c in v['claims']], hide_index=True)


def assignment_form(project, key, existing=None):
    a = existing or dict(title='', objective='', prompt='', deliverable='', criteria=[],
                         estimated_minutes=30, section='Methods', teacher_rationale='Teacher-created assignment.')
    with st.form(key):
        title = st.text_input('Assignment title', value=a['title'])
        objective = st.text_input('Learning objective', value=a['objective'])
        prompt = st.text_area('Task for the student', value=a['prompt'], height=130)
        deliverable = st.text_input('What the student should submit', value=a['deliverable'])
        criteria = st.text_area('Completion criteria (one per line)', value='\n'.join(a['criteria']))
        c1, c2 = st.columns(2)
        minutes = c1.number_input('Suggested minutes', min_value=5, max_value=240, value=a['estimated_minutes'], step=5)
        section = c2.text_input('Paper section / skill', value=a['section'])
        rationale = st.text_area('Private teaching rationale (excluded from handout)', value=a['teacher_rationale'])
        if st.form_submit_button('Approve handout' if existing else 'Save assignment proposal', type='primary'):
            edited = dict(title=title, objective=objective, prompt=prompt, deliverable=deliverable,
                          criteria=[c.strip() for c in criteria.splitlines() if c.strip()],
                          estimated_minutes=minutes, section=section, teacher_rationale=rationale)
            if existing:
                action('Approving the handout…', lambda: store.release_assignment(project['id'], a['id'], edited))
            else:
                action('Saving your assignment proposal…', lambda: store.add_assignments(project['id'], [edited], project['approved_reference'], len(project['evidence'])))


def submission_panel(project, assignment):
    aid = assignment['id']
    if assignment['status'] in ('ready', 'revision_requested'):
        with st.form('submission-' + aid):
            text = st.text_area('Paste the student’s own response', height=160)
            file = st.file_uploader('Or upload their work', type=['md', 'txt', 'tex'], key='student-work-' + aid)
            reflection = st.text_area('Student reflection / context (optional)')
            if st.form_submit_button('Record student submission'):
                action('Recording the original student work…', lambda: store.record_submission(project['id'], aid, uploaded_text(file) or text, reflection))
    if not assignment['submissions']:
        return
    latest = assignment['submissions'][-1]
    st.markdown('**Latest student submission**')
    st.caption(latest['created'])
    st.markdown(latest['text'])
    if latest['reflection']:
        st.markdown('**Reflection / context**\n\n' + latest['reflection'])
    if len(assignment['submissions']) > 1:
        with st.expander('Earlier submissions (preserved)'):
            for sub in assignment['submissions'][:-1]:
                st.caption(sub['created'])
                st.markdown(sub['text'])
    proposed = [f for f in assignment['feedback'] if f['status'] == 'proposed' and f['submission_id'] == latest['id']]
    draft = proposed[-1] if proposed else None
    if assignment['status'] == 'submitted':
        if st.button('Suggest feedback questions', key='ai-feedback-' + aid):
            action('Reviewing against the task and evidence…', lambda: coach.propose_feedback(project['id'], aid), ai=True)
        if draft:
            st.markdown('**Suggested feedback — review before giving it to the student**')
            st.markdown(feedback_markdown(draft))
            st.info('Private teacher notes: ' + draft['teacher_notes'])
        with st.form('final-feedback-' + aid + '-' + (draft['id'] if draft else 'manual')):
            message = st.text_area('Your feedback to give the student', value=feedback_markdown(draft) if draft else '', height=200)
            decision = st.radio('Next action', ['Request a revision', 'Mark complete'])
            if st.form_submit_button('Save reviewed feedback'):
                action('Saving your feedback…', lambda: store.release_feedback(project['id'], aid, latest['id'], message,
                        'complete' if decision == 'Mark complete' else 'revision_requested'))
    if draft and draft['next_task']:
        if st.button('Turn next-step suggestion into a new assignment proposal', key='followup-' + aid):
            followup = dict(title='Follow-up: ' + assignment['title'], objective=assignment['objective'],
                            prompt=draft['next_task'], deliverable='A student-written response addressing the feedback.',
                            criteria=['Address the feedback with reasoning and evidence.'], estimated_minutes=30,
                            section=assignment['section'], teacher_rationale=draft['teacher_notes'])
            action('Creating a follow-up proposal…', lambda: store.add_assignments(project['id'], [followup], project['approved_reference'], len(project['evidence'])))
    reviewed = [f for f in assignment['feedback'] if f['status'] == 'released']
    if reviewed:
        with st.expander('Reviewed feedback history', expanded=True):
            for feedback in reviewed:
                st.caption(feedback['created'] + ' · ' + feedback['decision'].replace('_', ' '))
                st.markdown(feedback['message'])
                st.download_button('Download feedback to give the student', feedback['message'],
                                   file_name='feedback.md', mime='text/markdown', key='feedback-download-' + feedback['id'])


def assignments_tab(project):
    st.subheader('Micro-assignments and student work')
    st.write('Review every proposal before exporting it. Give the handout to the student through your usual channel, then record their response here. Nothing is sent automatically.')
    with st.form('plan-assignments'):
        focus = st.text_area('What should the student work on next?', value='Suggest the next few useful tasks for a student who is mid-experiments. Keep the student responsible for all writing and related-work synthesis.')
        if st.form_submit_button('Propose micro-assignments', type='primary'):
            action('Planning the next writing steps…', lambda: coach.propose_assignments(project['id'], focus), ai=True)
    with st.expander('Create an assignment yourself (no API needed)'):
        assignment_form(project, 'manual-assignment')
    labels = dict(draft='Proposal', ready='Ready to give', submitted='Needs review', revision_requested='Revision requested', complete='Complete')
    for a in project['assignments']:
        with st.expander(f"{a['title']} · {labels[a['status']]}", expanded=a['status'] == 'submitted'):
            st.caption(f"Reference snapshot: {a['reference_id'][:8]} · Evidence entries at creation: {a['evidence_count']}")
            if a['reference_id'] != project['approved_reference'] or a['evidence_count'] != len(project['evidence']):
                st.warning('The reference or evidence has changed since this task was planned. Preserve this work; use a new follow-up task for changed interpretations.')
            if a['status'] == 'draft':
                assignment_form(project, 'edit-assignment-' + a['id'], a)
            else:
                handout = handout_markdown(store.assignment_handout(project['id'], a['id']))
                st.markdown(handout)
                st.download_button('Download assignment handout', handout, file_name='assignment-' + a['id'][:8] + '.md',
                                   mime='text/markdown', key='handout-' + a['id'])
                submission_panel(project, a)


def reading_tab(project):
    st.subheader('Reference suggestions and reading assignments')
    st.write('Find and check sources, then give the student reading questions. The student develops the themes and writes the related-work synthesis.')
    with st.form('suggest-sources'):
        topic = st.text_input('Reference topic / gap to investigate')
        if st.form_submit_button('Find reference suggestions'):
            if topic.strip():
                action('Searching for primary references…', lambda: coach.suggest_sources(project['id'], topic), ai=True)
            else:
                st.error('Enter a topic or research question.')
    with st.expander('Add a source yourself'):
        with st.form('manual-source'):
            title = st.text_input('Source title')
            url = st.text_input('Source link (HTTPS)')
            question = st.text_area('Reading question for the student')
            if st.form_submit_button('Add source suggestion'):
                def add():
                    if not title.strip():
                        raise ValueError('Enter a source title.')
                    store.add_sources(project['id'], [dict(title=title, url=url, reading_question=question,
                        reason='Teacher-added source.', citation='', verification='Teacher verification needed')])
                action('Saving the source suggestion…', add)
    for source in project['references']:
        with st.expander(source['title'] + ' · ' + source['status']):
            st.write(source['reason'])
            st.caption(source['verification'] + '. Check the title, authors, year and link before approving.')
            with st.form('source-' + source['id']):
                title = st.text_input('Title', value=source['title'])
                url = st.text_input('HTTPS link', value=source['url'])
                citation = st.text_area('Citation details', value=source['citation'])
                question = st.text_area('Student reading question', value=source['reading_question'])
                checked = st.checkbox('I checked this reference and its link.', value=source.get('teacher_checked', False))
                if st.form_submit_button('Approve reading suggestion'):
                    action('Saving the checked reading suggestion…', lambda: store.release_source(project['id'], source['id'], title, url, citation, question, checked))
    checked_sources = [r for r in project['references'] if r['status'] == 'approved']
    if checked_sources:
        handout = '# Reading suggestions\n\n' + '\n\n'.join(
            f"## {r['title']}\n{r['citation']}\n\n{r['url']}\n\n**Reading question:** {r['reading_question']}" for r in checked_sources)
        st.download_button('Download checked reading handout', handout, file_name='reading-assignment.md', mime='text/markdown')


st.sidebar.title('🎻 Teacher workspace')
st.sidebar.caption('Reference → assignments → feedback')
projects = store.list_projects()
options = ['new'] + [p['id'] for p in projects]
titles = {p['id']: p['title'] for p in projects}
if st.session_state.get('coach_pending_project') in options:
    st.session_state['coach_project'] = st.session_state.pop('coach_pending_project')
if st.session_state.get('coach_project') not in options:
    st.session_state['coach_project'] = projects[0]['id'] if projects else 'new'
project_id = st.sidebar.selectbox('Teaching project', options, key='coach_project',
    format_func=lambda p: '＋ New teaching project' if p == 'new' else titles[p])
st.sidebar.markdown('[Open standalone paper generator](?mode=writer)')
st.sidebar.caption(f'AI model: {DEFAULT_MODEL}')
if not credential_ready():
    st.sidebar.info('No API key configured. Manual projects, reference imports, assignments and feedback work now. AI suggestions need a key in .env and an app restart.')
st.title('Research Writing · Teacher Workspace')
st.caption('A living private reference. Small assignments. Student-authored papers.')
if project_id == 'new':
    create_project()
else:
    project = store.get(project_id)
    st.header(project['title'])
    tabs = st.tabs(['Overview', 'Evidence', 'Reference draft', 'Assignments', 'Reading'])
    with tabs[0]:
        overview(project)
    with tabs[1]:
        evidence_tab(project)
    with tabs[2]:
        reference_tab(project)
    with tabs[3]:
        assignments_tab(project)
    with tabs[4]:
        reading_tab(project)
