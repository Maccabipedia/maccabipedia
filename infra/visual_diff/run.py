"""Shoot the wiki as it is on the base commit and as this branch leaves it.

    uv run --with playwright --with pillow python infra/visual_diff/run.py \
        --base origin/master --out /tmp/visual [--page TITLE ...]

Needs the local wiki up (infra/local-wiki/). Only the files the wiki renders
from are switched - the skin, the Lua modules (with MediaWiki:Common.js) and
the LocalSettings config - so the scripts doing the switching never change
under themselves. It refuses to start when those paths have uncommitted edits,
because switching them would lose the edits; it puts them back on exit.

The pages are infra/visual_diff/pages.txt, the `<!-- visual-pages -->` block in
the PR_BODY environment variable, and every --page. Pages missing from the
local wiki are downloaded from production first (read only, Special:Export).
"""
import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compare  # noqa: E402

API = 'http://localhost:8080/api.php'
COMPOSE = ['docker', 'compose', '-f', 'infra/local-wiki/docker-compose.yml']
RENDERED_FROM = ['skins/Maccabipedia', 'infra/lua_modules', 'infra/local-wiki/config']
BODY_BLOCK = re.compile(r'<!--\s*visual-pages\s*\n(.*?)-->', re.S)
MAX_PAGES = 20


def git(*args: str) -> str:
    return subprocess.run(['git', *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def titles_from(text: str) -> list[str]:
    lines = (line.strip() for line in text.splitlines())
    return [line for line in lines if line and not line.startswith('#')]


def wanted_titles(extra: list[str]) -> list[str]:
    titles = titles_from((HERE / 'pages.txt').read_text(encoding='utf-8'))
    body = BODY_BLOCK.search(os.environ.get('PR_BODY', '').replace('\r\n', '\n'))
    if body:
        titles += titles_from(body.group(1))
    titles += extra
    unique = list(dict.fromkeys(titles))
    if len(unique) > MAX_PAGES:
        print(f'{len(unique)} pages asked for; shooting the first {MAX_PAGES}')
    return unique[:MAX_PAGES]


def missing_locally(titles: list[str]) -> list[str]:
    response = requests.post(API, data={'action': 'query', 'titles': '|'.join(titles),
                                        'format': 'json', 'formatversion': 2})
    response.raise_for_status()
    return [page['title'] for page in response.json()['query']['pages']
            if page.get('missing') or page.get('invalid')]


def import_from_production(titles: list[str], work: Path) -> None:
    manifest = work / 'visual-pages.manifest'
    manifest.write_text('\n'.join(titles) + '\n', encoding='utf-8')
    print(f'downloading {len(titles)} page(s) from production: {", ".join(titles)}')
    subprocess.run([sys.executable, 'infra/local-wiki/scripts/download_pages_from_prod.py',
                    'pages', str(manifest)], check=True)
    subprocess.run(['bash', 'infra/local-wiki/scripts/seed-content.sh', 'visual-pages'],
                   check=True)


def wait_for_wiki() -> None:
    for _ in range(60):
        try:
            if requests.get('http://localhost:8080/', timeout=10).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(3)
    raise SystemExit('the local wiki did not come back after the restart')


def switch_to(ref: str, titles: list[str], lua_changed: bool) -> None:
    """Make the wiki render from `ref`: files, then caches, then modules."""
    print(f'== rendering from {ref[:10]}')
    git('restore', f'--source={ref}', '--worktree', '--', *RENDERED_FROM)
    # A restart drops APCu and OPcache, so no skin.json, PHP or ResourceLoader
    # state from the other commit survives the switch.
    subprocess.run([*COMPOSE, 'restart', 'mediawiki'], check=True, capture_output=True)
    wait_for_wiki()
    if not lua_changed:
        return
    subprocess.run([sys.executable, 'infra/lua_modules/deploy_modules.py'], check=True)
    # Module output sits in the parser cache, so only a purge shows the new one.
    # Not done for skin-only changes: every render looks images up on production.
    response = requests.post(API, data={'action': 'purge', 'titles': '|'.join(titles),
                                        'forcelinkupdate': 1, 'format': 'json'})
    response.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='origin/master',
                        help='compared against the merge base of HEAD and this ref')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--page', action='append', default=[])
    parser.add_argument('--image-base', default='.')
    parser.add_argument('--header', default='')
    options = parser.parse_args()

    import shoot  # here, not at the top: it needs playwright, the tests do not

    if git('status', '--porcelain', '--', *RENDERED_FROM):
        raise SystemExit(f'uncommitted changes under {RENDERED_FROM}; commit them first')
    head = git('rev-parse', 'HEAD')
    base = git('merge-base', 'HEAD', options.base)
    lua_changed = bool(git('diff', '--name-only', base, head, '--', 'infra/lua_modules'))
    options.out.mkdir(parents=True, exist_ok=True)

    titles = wanted_titles(options.page)
    missing = missing_locally(titles)
    if missing:
        import_from_production(missing, options.out)
        still_missing = missing_locally(missing)
        titles = [t for t in titles if t not in still_missing]
        if still_missing:
            print(f'not on production either, skipped: {", ".join(still_missing)}')

    try:
        switch_to(base, titles, lua_changed)
        shoot.shoot(titles, options.out / 'before')
        shoot.shoot(titles, options.out / 'again')
    finally:
        switch_to(head, titles, lua_changed)
    shoot.shoot(titles, options.out / 'after')

    results = compare.compare(options.out / 'before', options.out / 'after',
                              options.out / 'again', options.out / 'images')
    text = compare.comment(results, options.image_base.rstrip('/'),
                           options.header or f'`{base[:7]}` → `{head[:7]}`')
    (options.out / 'images' / 'comment.md').write_text(text, encoding='utf-8')
    for verdict in ('changed', 'unstable', 'same'):
        print(f'{verdict}: {sum(r["verdict"] == verdict for r in results)}')


if __name__ == '__main__':
    main()
