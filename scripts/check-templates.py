"""Compile both supplied templates using real local TeX tools; no API calls."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.runtime_config import ROOT, setup_local_tools

setup_local_tools()
for template in ('cvpr2025', 'iclr2025'):
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / template
        shutil.copytree(ROOT / 'templates' / template, work)
        source = work / 'template.tex'
        source.write_text(source.read_text().replace(r'\bibliography{', r'\nocite{*}' + '\n' + r'\bibliography{'))
        commands = [
            ['pdflatex', '-halt-on-error', '-interaction=nonstopmode', 'template.tex'],
            ['bibtex', 'template'],
            ['pdflatex', '-halt-on-error', '-interaction=nonstopmode', 'template.tex'],
            ['pdflatex', '-halt-on-error', '-interaction=nonstopmode', 'template.tex'],
        ]
        for command in commands:
            result = subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=60)
            if result.returncode:
                print(result.stdout[-4000:])
                print(result.stderr)
                raise SystemExit(f'{template}: {command[0]} failed')
        assert (work / 'template.pdf').is_file()
        print(f'{template}: compiled successfully')
