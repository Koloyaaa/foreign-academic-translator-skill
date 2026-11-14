from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def skills(tier):
    root = ROOT / 'skills' / tier / 'skills'
    return {path.name: path for path in root.iterdir() if path.is_dir() and (path / 'SKILL.md').is_file()}


def test_each_tier_has_its_own_valid_skill_entries():
    for tier in ('lite', 'plus', 'pro', 'max'):
        entries = skills(tier)
        assert entries, tier
        for name, directory in entries.items():
            assert not directory.is_symlink()
            content = (directory / 'SKILL.md').read_text(encoding='utf-8')
            assert re.search(r'^name:\s*' + re.escape(name) + r'\s*$', content, re.MULTILINE), (tier, name)


def test_pro_and_max_each_contain_the_complete_new_group():
    assert len(skills('max')) == 11
    assert set(skills('pro')) == set(skills('max'))


def test_max_contains_runtime_scripts():
    maximum = ROOT / 'skills' / 'max' / 'skills' / 'translation-orchestrator' / 'scripts'
    for name in ('workflow_state.py', 'builder.py', 'text_extractor.py'):
        assert (maximum / name).is_file()
