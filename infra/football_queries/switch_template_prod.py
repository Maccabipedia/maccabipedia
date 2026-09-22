"""Switch ONE production template to a checked candidate, revert it, or purge its callers.

    uv run python infra/football_queries/switch_template_prod.py apply  --title T --candidate FILE --expect-sha1 PREFIX --summary TEXT
    uv run python infra/football_queries/switch_template_prod.py revert --title T
    uv run python infra/football_queries/switch_template_prod.py purge  --title T [--start N]

The last step of a rollout whose comparison already passed (the candidate is
what compare_*.py rendered against production):

apply  - refuses unless the live template's sha1 starts with --expect-sha1
         (the text the comparison ran against); saves that text and the new
         revision to .claude/tmp/template_switches/; writes the candidate as
         multipart (the firewall refuses urlencoded edits) and reads it back.
revert - refuses unless the live text is still exactly what `apply` wrote,
         then writes the saved previous text back the same way.
purge  - purges every page that transcludes the template through the bot's
         session (no anonymous 30-a-minute limit), 10 per request, 3 s apart,
         stopping at the first failure.

It edits one page per run and nothing else.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, 'infra/football_queries')
import deploy_modules_prod as deploy  # noqa: E402

RECORDS = Path('.claude/tmp/template_switches')


def record_path(title: str) -> Path:
    return RECORDS / (hashlib.sha1(title.encode('utf-8')).hexdigest()[:12] + '.json')


def live_revision(connection, title: str) -> dict:
    response = connection.simple_request(action='query', titles=title, prop='revisions',
                                         rvprop='sha1|ids|content', rvslots='main', format='json').submit()
    page = next(iter(response['query']['pages'].values()))
    if 'revisions' not in page:
        raise SystemExit(f'{title} does not exist - refusing')
    revision = page['revisions'][0]
    return {'sha1': revision['sha1'], 'revid': revision['revid'],
            'text': revision['slots']['main']['*']}


def apply(connection, options) -> None:
    live = live_revision(connection, options.title)
    if not options.expect_sha1 or not live['sha1'].startswith(options.expect_sha1):
        raise SystemExit(f'{options.title} is at sha1 {live["sha1"]}, not {options.expect_sha1} '
                         '- the comparison ran against other text; refusing')
    candidate = Path(options.candidate).read_text(encoding='utf-8')
    if candidate.strip() == live['text'].strip():
        raise SystemExit('the candidate equals the live text - nothing to switch')
    RECORDS.mkdir(parents=True, exist_ok=True)
    record = {'title': options.title, 'previous_revid': live['revid'], 'previous_text': live['text'],
              'written_text': candidate}
    record_path(options.title).write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
    deploy.SUMMARY = options.summary
    result = deploy.publish(connection, options.title, candidate)
    print(f'{options.title}: {result} (previous revision {live["revid"]}, saved to {record_path(options.title)})')
    if result != 'ok':
        sys.exit(1)


def revert(connection, options) -> None:
    record = json.loads(record_path(options.title).read_text(encoding='utf-8'))
    live = live_revision(connection, options.title)
    if live['text'].strip() != record['written_text'].strip():
        raise SystemExit('the template was edited after the switch - refusing to overwrite it')
    deploy.SUMMARY = f'שחזור לגרסה {record["previous_revid"]}'
    result = deploy.publish(connection, options.title, record['previous_text'])
    print(f'{options.title}: reverted to revision {record["previous_revid"]} text: {result}')
    if result != 'ok':
        sys.exit(1)


def purge(connection, options) -> None:
    pages = sorted(deploy.callers(connection, options.title))
    for start in range(options.start, len(pages), 10):
        batch = pages[start:start + 10]
        try:
            deploy.purge(connection, batch)
        except Exception as error:  # noqa: BLE001 - report where it stopped, never push on
            raise SystemExit(f'purge stopped at {start}/{len(pages)}: {error} (resume with --start {start})')
        print(f'purged {start + len(batch)}/{len(pages)}', flush=True)
        time.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=('apply', 'revert', 'purge'))
    parser.add_argument('--title', required=True)
    parser.add_argument('--candidate')
    parser.add_argument('--expect-sha1')
    parser.add_argument('--summary', default='')
    parser.add_argument('--start', type=int, default=0)
    options = parser.parse_args()
    if options.mode == 'apply' and not (options.candidate and options.expect_sha1 and options.summary):
        parser.error('apply needs --candidate, --expect-sha1 and --summary')
    connection = deploy.site()
    {'apply': apply, 'revert': revert, 'purge': purge}[options.mode](connection, options)


if __name__ == '__main__':
    main()
