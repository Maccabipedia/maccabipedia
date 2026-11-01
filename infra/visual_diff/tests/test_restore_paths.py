"""Switching the rendered-from paths to the base and back leaves HEAD exactly."""
import subprocess

import run


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def commit_all(repo, message):
    git(repo, 'add', '-A')
    git(repo, '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', message)
    return git(repo, 'rev-parse', 'HEAD')


def test_base_only_and_head_only_files_do_not_leak(tmp_path, monkeypatch):
    skin = tmp_path / 'skin'
    skin.mkdir()
    git(tmp_path, 'init', '-q')
    (skin / 'old.less').write_text('base only')
    (skin / 'keep.less').write_text('base')
    base = commit_all(tmp_path, 'base')
    (skin / 'old.less').unlink()
    (skin / 'keep.less').write_text('head')
    (skin / 'new.less').write_text('head only')
    commit_all(tmp_path, 'head')

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run, 'RENDERED_FROM', ['skin'])

    run.restore_paths(base)
    assert sorted(p.name for p in skin.iterdir()) == ['keep.less', 'old.less']
    assert (skin / 'keep.less').read_text() == 'base'

    run.restore_paths('HEAD')
    assert sorted(p.name for p in skin.iterdir()) == ['keep.less', 'new.less']
    assert (skin / 'keep.less').read_text() == 'head'
    assert git(tmp_path, 'status', '--porcelain') == ''
