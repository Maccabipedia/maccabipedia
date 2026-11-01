"""Compare before/after screenshots and write the PR comment (used by run.py).

`again` is a second shot of the BEFORE state. A page that differs between
two shots of the same code (a random box, a clock, a slider) is reported as
unstable rather than as changed, so its noise cannot pass for the PR's change.

Writes the images the comment shows (only for shots that differ) and
report.json into the output directory; comment() builds the markdown.
"""
import json
from pathlib import Path

from PIL import Image, ImageChops

MARKER = '<!-- visual-diff -->'
# Share of pixels that must differ before a shot counts as changed. Anti-aliasing
# alone moves a few pixels between identical renders.
THRESHOLD = 0.0005


def changed_share(first: Path, second: Path) -> float:
    a, b = Image.open(first).convert('RGB'), Image.open(second).convert('RGB')
    if a.size != b.size:
        return 1.0
    diff = ImageChops.difference(a, b).convert('L').point(lambda v: 255 if v > 16 else 0)
    histogram = diff.histogram()
    return histogram[255] / (a.size[0] * a.size[1])


def save_jpeg(source: Path, target: Path) -> None:
    Image.open(source).convert('RGB').save(target, 'JPEG', quality=85, optimize=True)


def compare(before: Path, after: Path, again: Path, out: Path) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    shots = json.loads((after / 'shots.json').read_text(encoding='utf-8'))
    before_status = {s['file']: s['status'] for s in
                     json.loads((before / 'shots.json').read_text(encoding='utf-8'))}
    results = []
    for shot in shots:
        name = shot['file']
        noise = changed_share(before / name, again / name)
        share = changed_share(before / name, after / name)
        if noise > THRESHOLD:
            verdict = 'unstable'
        elif share > THRESHOLD:
            verdict = 'changed'
        else:
            verdict = 'same'
        stem = name.removesuffix('.png')
        if verdict != 'same':
            save_jpeg(before / name, out / f'{stem}-before.jpg')
            save_jpeg(after / name, out / f'{stem}-after.jpg')
        results.append({**shot, 'stem': stem, 'verdict': verdict,
                        'share': round(share, 4), 'noise': round(noise, 4),
                        'before_status': before_status.get(name)})
    (out / 'report.json').write_text(json.dumps(results, ensure_ascii=False, indent=1),
                                     encoding='utf-8')
    return results


def pair_table(result: dict, image_base: str) -> str:
    before = f'{image_base}/{result["stem"]}-before.jpg'
    after = f'{image_base}/{result["stem"]}-after.jpg'
    width = 420 if result['viewport'] == 'desktop' else 260
    return ('| Before | After |\n|---|---|\n'
            f'| <a href="{before}"><img src="{before}" width="{width}"></a> '
            f'| <a href="{after}"><img src="{after}" width="{width}"></a> |\n')


def comment(results: list[dict], image_base: str, header: str) -> str:
    changed = [r for r in results if r['verdict'] == 'changed']
    unstable = [r for r in results if r['verdict'] == 'unstable']
    same = [r for r in results if r['verdict'] == 'same']
    lines = [MARKER, '## Before / after', '', header, '']
    if changed:
        lines.append(f'**{len(changed)} of {len(results)} shots changed.** '
                     'Click an image for full size.\n')
    else:
        lines.append(f'**No visual change** in any of the {len(results)} shots.\n')
    for result in changed:
        lines.append(f'<details open><summary><b>{result["title"]}</b> · '
                     f'{result["viewport"]} · {result["share"]:.1%} of pixels'
                     '</summary>\n')
        lines.append(pair_table(result, image_base))
        lines.append('</details>\n')
    for result in unstable:
        lines.append(f'<details><summary>{result["title"]} · {result["viewport"]} · '
                     'unstable: differs between two shots of the same code, so a '
                     'change here cannot be told from noise</summary>\n')
        lines.append(pair_table(result, image_base))
        lines.append('</details>\n')
    broken = [r for r in results if r['status'] != 200 or r['before_status'] != 200]
    if broken:
        lines.append('**Pages that did not load (HTTP status before → after):** ' + ', '.join(
            f'{r["title"]} ({r["before_status"]} → {r["status"]})' for r in broken
            if r['viewport'] == 'desktop') + '\n')
    if same:
        lines.append('<details><summary>Unchanged: ' + str(len(same)) + ' shots</summary>\n\n'
                     + '\n'.join(f'- {r["title"]} · {r["viewport"]}' for r in same)
                     + '\n</details>\n')
    lines.append('<sub>Rendered on the CI local wiki (snapshot data, logged out) by '
                 '`.github/workflows/visual_diff.yaml`. To shoot more pages, add a '
                 '`<!-- visual-pages ... -->` block to the PR description, one title per '
                 'line. See `.claude/visual_diff.md`.</sub>')
    return '\n'.join(lines) + '\n'
