# <div align="center">🎻 PaperOrchestra: A Multi-Agent Framework for Automated AI Research Paper Writing</div>
<div align="center">Yiwen Song<sup>1</sup>, Yale Song<sup>1</sup>, Tomas Pfister<sup>1</sup>, and Jinsung Yoon<sup>1</sup></div>
<div align="center"><sup>1</sup>Google Cloud AI Research</div>
<br><br>

PaperOrchestra is a multi-agent framework for automated AI research paper writing. It flexibly transforms unconstrained pre-writing materials (ideas and experimental logs) into submission-ready LaTeX manuscripts, including comprehensive literature synthesis and generated visuals, such as plots and conceptual diagrams.

Acting like an orchestrated team of specialized agents, it handles outline generation, literature review, section writing, content refinement, and plotting to close the gap between raw research materials and submission ready papers.

<div align="center">
  <img src="assets/overview.png" alt="PaperOrchestra Overview" width="90%"/>
</div>

## Key Features

- **Multi-Agent Pipeline**: Orchestrates specialized agents (Outline, Literature Review, Section Writing, Content Refinement, Plotting) for end-to-end paper generation.
- **Comprehensive Literature Synthesis**: Automatically searches, prioritizes, and integrates relevant literature into the manuscript.
- **Visuals Generation**: Generates plots and supports the inclusion of conceptual diagrams.
- **LaTeX Automation**: Produces submission-ready LaTeX manuscripts adhering to target conference templates.

## Local setup in this fork

Python 3.11 or newer is required; Python 3.12 was verified on Apple Silicon.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
cp .env.example .env
# Edit .env and set OPENAI_API_KEY.
./scripts/install-tex-macos.sh  # macOS; alternatively install a TeX distribution
.venv/bin/python paper_writing_cli.py --check
./scripts/run-local.sh
```

Open <http://127.0.0.1:8501> for the **teacher-only writing workspace**.
There is no student login or student portal. The teacher gives assignments and
receives student work through their existing classroom workflow.

### Teacher workflow

1. **Create a project:** add the student's idea, experimental methodology, current
   results, learning goals, target length and optional conference/custom LaTeX guide.
   The sample-materials button fills the form without calling a model.
2. **Record evidence:** append completed, preliminary or planned experiment entries.
   Add corrections as new entries naming the earlier evidence ID.
3. **Prepare a private reference:** generate a proposal or import a teacher-written
   Markdown/text draft. Review the manuscript and claim/evidence ledger, edit them,
   and approve a new snapshot. Pending and historical versions are retained.
4. **Plan micro-assignments:** ask for the next few tasks, or write them yourself.
   Edit each task, deliverable and completion criteria before approving its handout.
   Download the Markdown handout to give to the student. Private reference content
   and teaching rationale are excluded from the handout export.
5. **Record student work:** paste or upload the student's own response. Review
   passage-specific feedback suggestions, edit your feedback and mark the task
   complete or request revision. Earlier submissions and feedback remain available.
   Turn a next-step suggestion into a new assignment proposal when useful.
6. **Update as results arrive:** new evidence leaves the approved reference and all
   student work unchanged. Generate an update, inspect the text diff, changed claims
   and suggested assignment impacts, then approve it. Proposals based on stale
   evidence cannot replace a newer reference. Existing tasks are preserved; use
   new follow-ups when an interpretation changes.
7. **Suggest reading:** find reference candidates or add your own. Check citation
   details and the source link, edit the reading question, and approve a reading
   handout. The student develops themes and writes the related-work synthesis.

The reference is displayed, edited and exported as Markdown; the template and page
budget guide its structure, but this mode does not compile a page-exact PDF.
The original PDF-generation interface is available through **Open standalone paper
generator**, or at <http://127.0.0.1:8501/?mode=writer>. Its **Load CVPR Example**
button supplies an idea, experiment log and figure. Standalone paper-generation
runs are saved under `demo_logs/`.

Teacher projects persist in `coaching_data/workspace.sqlite3` (ignored by Git).
The Overview tab exports a private JSON project record including all history.
For an alternate local database location, set `PAPER_ORCHESTRA_COACH_DB` before
starting the app. No messages, assignments or feedback are sent automatically.
Restart the server after changing `.env`. The manual teacher workflow works
without a model API key; AI reference, assignment, feedback and source suggestions
need a key. Student work is never automatically rewritten.

The UI opens without credentials. The default pipeline uses OpenAI throughout:
outline, literature discovery with web search, section writing, peer review,
PDF refinement and visual formatting review. Set `OPENAI_API_KEY` in `.env`.
Gemini credentials are only needed when explicitly selecting Gemini models.
`--check` verifies configuration presence and executables; it does not validate
credentials or model access. `PAPER_ORCHESTRA_MODEL` changes the default model
(currently `gpt-6-astra`); CLI model arguments can override individual stages.
Choose a model that supports the Responses API, web search, and PDF/image inputs.

OpenAI plots and conceptual diagrams are generated as matplotlib code and
rendered locally, so no separate image model or Google credentials are required.
Gemini runs retain the original raster diagram generator. The optional
PaperBanana reference dataset is not bundled; figure generation falls back to
running without those examples. Semantic Scholar is still used for citation
verification; its API key is optional.

The OpenAI adapter uses the [Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses),
[web search](https://developers.openai.com/api/docs/guides/tools-web-search),
and native [PDF inputs](https://developers.openai.com/api/docs/guides/file-inputs).
API usage, including hosted search, is billed to the configured API account.
The automated tests fake model responses and execute real local LaTeX/figure
rendering; a full live generation run requires a valid key and model access.

The lock file records the tested Python dependencies. For other platforms, install
`requirements.txt` if a platform-specific locked dependency is unavailable.
On Linux, install TeX Live providing `pdflatex`, `bibtex`, and the packages used
by the CVPR/ICLR templates. Portable TeX binaries under `.tools/TinyTeX/bin/`
and standard macOS TeX binaries are discovered automatically.

Validation (no paid model calls):

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/check-templates.py
```

This fork fixes import-time credential failures, macOS subprocess startup, CLI
failure exit codes, and required email entry. Credentials and local environments
are ignored by Git. The local launcher binds only to `127.0.0.1`.

## Installation

1.  **Environment Setup**: The project relies on a Conda environment named `paper_orchestra`. You can set up a similar environment with Python 3.11 and install the required dependencies.
    ```bash
    conda create -n paper_orchestra python=3.11
    conda activate paper_orchestra
    pip install -r requirements.txt
    ```

2.  **Environment Variables**: Create a `.env` file in the root of the project and add your API keys:
    ```env
    # Add keys if you have them, otherwise leave them empty
    # You need to specify related keys if you want to use the model
    # The default OpenAI pipeline needs OPENAI_API_KEY. For Gemini models, specify either VERTEX_AI_PROJECT and VERTEX_AI_LOCATION, or GEMINI_API_KEY
    # If you want to use OpenAI models, you need to specify OPENAI_API_KEY
    
    SEMANTIC_SCHOLAR_API_KEY=your_semantic_scholar_api_key
    OPENAI_API_KEY=your_openai_api_key
    VERTEX_AI_PROJECT=your_vertex_ai_project
    VERTEX_AI_LOCATION=your_vertex_ai_location
    GEMINI_API_KEY=your_gemini_api_key

    # if you want to run demo and send emails to yourself at the end, set these 2 fields as well
    SMTP_EMAIL=your_email
    SMTP_PASSWORD=your_password
    ```

## Dataset

The dataset used for paper generation is **not included** in this code repository. It will be released separately at a later date.
Once available, you should download the dataset and place it under the `datasets/` directory.

## Usage

You can run the paper generation pipeline using the provided bash script or directly via the Python CLI.

### Using the Bash Script
```bash
./paper_writing_cli.sh
```

### Using the Python CLI directly
```bash
python paper_writing_cli.py \
  --raw_materials_dir /path_to_your_raw_materials/ \
  --latex_template_dir /path_to_your_latex_template/ \
  --output_dir /path_to_your_output_folder/ \
  --use_plotting true
```

### Key Arguments
*   `--raw_materials_dir`: (Required) Directory containing the raw materials (e.g., idea and experimental log).
*   `--latex_template_dir`: (Required) Directory containing the LaTeX template (e.g., `templates/cvpr2025`).
*   `--output_dir`: Directory to output the generated paper. If not specified, an automatic folder with a timestamp is created.
*   `--use_plotting`: Enable the plotting agent workflow to generate figures from code (Default: `False`).
*   `--writer_model_name`: LLM for writer and literature agents.
*   `--reflection_model_name`: LLM for reflection agents.

### Interactive Demo

We provide an interactive Streamlit demo for the paper generation pipeline. For instructions on how to run and use it, please refer to the [README.md](frontend/README.md) in the `frontend` directory.

## Project Structure

*   `autoraters/`: Contains scripts for automated evaluation.
*   `methods/`: Core logic for agents and pipeline execution.
*   `templates/`: LaTeX templates for target conferences, you can add your own template by creating a new subfolder under this directory.
*   `utils/`: Utility functions for API calls, PDF handling, etc.

## Citation

If you find this repo or our paper helpful, please cite it as follows:

```bibtex
@article{song2026paperorchestra,
  title={PaperOrchestra: A Multi-Agent Framework for Automated AI Research Paper Writing},
  author={Song, Yiwen and Song, Yale and Pfister, Tomas and Yoon, Jinsung},
  journal={arXiv preprint arXiv:2604.05018},
  year={2026}
}
```

# Disclaimer

This is not an officially supported Google product.
