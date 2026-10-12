"""Build the standalone, standard-library-only customer delivery."""
import hashlib
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    'QUICKSTART.md', 'sales/PRODUCT.md', 'sales/SETUP.md', 'sales/FAQ.md',
    'agent/__init__.py', 'agent/README.md', 'agent/main.py', 'agent/pipeline.py',
    'agent/proposal.py', 'agent/scorer.py', 'agent/eligibility.py',
    'agent/job_normalizer.py', 'agent/report.py', 'agent/config.json',
    'agent/profile.example.json', 'agent/jobs.example.json',
    'tests/test_cli.py', 'tests/test_eligibility.py', 'tests/test_normalizer.py',
    'tests/test_pipeline.py', 'tests/test_proposal.py', 'tests/test_scorer.py',
]


def build(destination=None):
    destination = Path(destination) if destination else ROOT / 'dist' / 'MexAy_Job_Draft_Assistant.zip'
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
        for filename in FILES:
            archive.write(ROOT / filename, 'MexAy_Job_Draft_Assistant/' + filename)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix('.sha256').write_text(f'{digest}  {destination.name}\n', encoding='utf-8')
    return destination


if __name__ == '__main__':
    print(build())
