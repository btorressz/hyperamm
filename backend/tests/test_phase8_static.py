from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]


def test_phase8_adds_no_github_actions_directory():
    assert not (ROOT/'.github').exists()


def test_repository_contains_no_forbidden_oracle_provider_token():
    forbidden=re.compile(r'\bpyth\b',re.IGNORECASE)
    candidates=[
        ROOT/'backend'/'app',
        ROOT/'backend'/'tests',
        ROOT/'docs',
        ROOT/'README.md',
        ROOT/'.env.example',
        ROOT/'backend'/'pyproject.toml',
    ]
    hits=[]
    for candidate in candidates:
        paths=[candidate] if candidate.is_file() else list(candidate.rglob('*'))
        for path in paths:
            if not path.is_file() or path.suffix.lower() not in {'.py','.md','.toml','.txt','.example',''}:
                continue
            try:text=path.read_text()
            except UnicodeDecodeError:continue
            if forbidden.search(text):
                hits.append(str(path.relative_to(ROOT)))
    assert hits==[]


def test_example_env_contains_no_committed_provider_or_signing_secrets():
    text=(ROOT/'.env.example').read_text()
    for key in ('HYPERLIQUID_PRIVATE_KEY','REDSTONE_API_KEY','COINGECKO_API_KEY'):
        line=next(line for line in text.splitlines() if line.startswith(key+'='))
        assert line==key+'='
