# Paper Orchestra Frontend

Run from the repository root after following the setup in the main README:

```bash
./scripts/run-local.sh
```

Open <http://127.0.0.1:8501> for the teacher-only workspace. No student login or
portal is included. Create a project, record evidence, review a private reference,
approve and export assignment handouts, record student work, and review feedback.
New results create proposed reference updates for teacher review; earlier reference
versions, assignments and student submissions remain intact. The Reading tab builds
teacher-checked reference suggestions and reading questions, without writing the
student's related-work synthesis.

The reference document is edited and exported in Markdown. Conference/custom LaTeX
source can guide its structure. Teacher records are saved locally in the Git-ignored
`coaching_data/workspace.sqlite3` database. Manual input and review do not require an
API key. AI suggestions use the configured model and key from `.env`; restart after
changing them.

The original standalone paper generator is available from the sidebar, or at
<http://127.0.0.1:8501/?mode=writer>. It can still generate LaTeX and PDFs. Its
background CLI process can remain running if the server is stopped. Use
`pgrep -fl paper_writing_cli.py` to identify that specific process before stopping it.
