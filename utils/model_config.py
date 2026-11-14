"""Provider selection without importing either provider SDK."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def is_openai_model(model_name):
    return model_name.lower().startswith(('gpt-', 'chatgpt-', 'o1', 'o3', 'o4'))


DEFAULT_MODEL = os.getenv('PAPER_ORCHESTRA_MODEL', 'gpt-6-astra')
