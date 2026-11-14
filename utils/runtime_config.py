"""Local tool discovery and actionable checks shared by the CLI and demo."""
import os
from pathlib import Path
import shutil

from dotenv import load_dotenv
from utils.model_config import DEFAULT_MODEL, is_openai_model

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')


def setup_local_tools():
    candidates = [ROOT / '.tools' / 'TinyTeX' / 'bin', ROOT / '.tools' / '.TinyTeX' / 'bin']
    paths = []
    for candidate in candidates:
        if candidate.is_dir():
            paths.extend(str(p) for p in candidate.iterdir() if p.is_dir())
    if Path('/Library/TeX/texbin').is_dir():
        paths.append('/Library/TeX/texbin')
    if paths:
        os.environ['PATH'] = os.pathsep.join(paths + [os.environ.get('PATH', '')])
    cache = ROOT / '.cache'
    os.environ.setdefault('MPLCONFIGDIR', str(cache / 'matplotlib'))


def generation_errors(model_names=None):
    setup_local_tools()
    errors = []
    models = model_names or [DEFAULT_MODEL]
    if any(is_openai_model(model) for model in models) and not os.getenv('OPENAI_API_KEY'):
        errors.append('Set OPENAI_API_KEY in .env before using OpenAI models.')
    if any(not is_openai_model(model) for model in models) and not (
            os.getenv('GEMINI_API_KEY') or
            (os.getenv('VERTEX_AI_PROJECT') and os.getenv('VERTEX_AI_LOCATION'))):
        errors.append('Set GEMINI_API_KEY (or Vertex project and location) in .env before using Gemini models.')
    missing = [tool for tool in ('pdflatex', 'bibtex') if not shutil.which(tool)]
    if missing:
        errors.append('Install a TeX distribution providing: ' + ', '.join(missing))
    return errors
