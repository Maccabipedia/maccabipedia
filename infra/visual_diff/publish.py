"""Put a run's images on the visual-diffs branch and post (or update) the one
before/after comment on the pull request. Called by visual_diff.yaml.

    uv run python infra/visual_diff/publish.py IMAGES_DIR PATH_ON_BRANCH PR_NUMBER

Needs GH_TOKEN (contents: write, pull-requests: write) and GITHUB_REPOSITORY.
GitHub has no API for attaching an image to a comment, so the images live on an
orphan branch of this public repo and the comment links their raw URLs. Each
run adds a folder and nothing is rewritten, so older comments keep their images.

Through the Git Data API, not a clone: the branch only grows, and a clone, even
a shallow one, would download every image ever posted on every run.
"""
import base64
import os
import sys
import time
from pathlib import Path

import requests

BRANCH = 'visual-diffs'
MARKER = '<!-- visual-diff -->'
BOT = 'github-actions[bot]'


class GitHub:
    def __init__(self) -> None:
        self.repo = os.environ['GITHUB_REPOSITORY']
        self.session = requests.Session()
        self.session.headers.update({'Authorization': f'Bearer {os.environ["GH_TOKEN"]}',
                                     'Accept': 'application/vnd.github+json'})

    def call(self, method: str, path: str, ok=(200, 201), **kwargs) -> requests.Response:
        response = self.session.request(method, f'https://api.github.com/repos/{self.repo}/{path}',
                                        timeout=60, **kwargs)
        if response.status_code not in ok:
            raise SystemExit(f'{method} {path}: {response.status_code} {response.text[:300]}')
        return response


def push_images(github: GitHub, images: list[Path], dest: str, pr: str) -> None:
    tree_entries = []
    for image in images:
        blob = github.call('POST', 'git/blobs', json={
            'content': base64.b64encode(image.read_bytes()).decode(), 'encoding': 'base64'})
        tree_entries.append({'path': f'{dest}/{image.name}', 'mode': '100644', 'type': 'blob',
                             'sha': blob.json()['sha']})

    # Another PR's run may move the branch between our read and our update; the
    # update is then refused (not a fast-forward), and we build on the new tip.
    for attempt in range(1, 6):
        ref = github.call('GET', f'git/ref/heads/{BRANCH}', ok=(200, 404))
        tip = ref.json()['object']['sha'] if ref.status_code == 200 else None
        tree_request = {'tree': tree_entries}
        if tip:
            tree_request['base_tree'] = github.call('GET', f'git/commits/{tip}').json()['tree']['sha']
        tree = github.call('POST', 'git/trees', json=tree_request).json()['sha']
        commit = github.call('POST', 'git/commits', json={
            'message': f'Before/after images for PR #{pr} ({dest})', 'tree': tree,
            'parents': [tip] if tip else []}).json()['sha']
        if tip:
            moved = github.call('PATCH', f'git/refs/heads/{BRANCH}', ok=(200, 422),
                                json={'sha': commit, 'force': False})
        else:
            moved = github.call('POST', 'git/refs', ok=(201, 422),
                                json={'ref': f'refs/heads/{BRANCH}', 'sha': commit})
        if moved.status_code in (200, 201):
            print(f'{len(images)} image(s) on {BRANCH}/{dest}')
            return
        print(f'branch moved under us (attempt {attempt}), retrying')
        time.sleep(attempt * 3)
    raise SystemExit(f'could not update {BRANCH} after 5 attempts')


def post_comment(github: GitHub, body: str, pr: str) -> None:
    page = 1
    while True:
        comments = github.call('GET', f'issues/{pr}/comments',
                               params={'per_page': 100, 'page': page}).json()
        for existing in comments:
            if existing['user']['login'] == BOT and existing['body'].startswith(MARKER):
                url = github.call('PATCH', f'issues/comments/{existing["id"]}',
                                  json={'body': body}).json()['html_url']
                print(f'updated {url}')
                return
        if len(comments) < 100:
            break
        page += 1
    url = github.call('POST', f'issues/{pr}/comments', json={'body': body}).json()['html_url']
    print(f'posted {url}')


def main() -> None:
    images_dir, dest, pr = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    github = GitHub()
    images = sorted(images_dir.glob('*.jpg'))
    if images:
        push_images(github, images, dest, pr)
    post_comment(github, (images_dir / 'comment.md').read_text(encoding='utf-8'), pr)


if __name__ == '__main__':
    main()
