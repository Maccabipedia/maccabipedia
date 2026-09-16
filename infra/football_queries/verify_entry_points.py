"""Each entry point must accept exactly what the template it replaces accepts.

A shim declares `replaces` and a list of parameters. Nothing keeps the two in
step by itself, and both ways of drifting are silent on the page:

  * a parameter the template has and the shim lacks -> the page passes it, the
    shim refuses it, and a red Lua error replaces the number;
  * a parameter the shim has and the template lacks -> the shim answers a
    question the template could not be asked, and the number looks fine.

This found a real one: the harness pointed כמות אירועי שחקן at `gameDataCount`,
whose list belongs to כמות נתוני משחק, so every event filter was refused.

    uv run python infra/football_queries/verify_entry_points.py

Reads the templates from the LOCAL wiki - they are seeded from production by
compare_rendered_blocks.py --seed. Exit code is the number of mismatches.
"""
import re
import subprocess
import sys
from pathlib import Path

COMPOSE_FILE = 'infra/local-wiki/docker-compose.yml'
FIELDS = Path('infra/football_queries/Module_FootballQueries_Fields.lua')

# Template parameters that are deliberately not entry-point parameters, with
# the reason. Anything not listed here has to match.
EXPECTED_ABSENT = {
    # כמות אירועי שחקן reads this twice in its body to switch alias expansion
    # off. The module has no such switch - alias expansion is a property of
    # the filter kind (opponentAliases, stadiumAliases), not a flag - so the
    # entry point does not declare it and a page that passes it gets a visible
    # error from separate() rather than a silently unexpanded query.
    'ללא מפעלים מקושרים': 'alias expansion is a filter kind here, not a flag',
}

# The Lua that dumps the declarations. Reading them by regex from the data page
# would be a second, weaker parser of the same file.
DUMP = '''
local fields = dofile('%s')
for name, entry in pairs(fields.entryPoints) do
    local names = {}
    for _, filter in ipairs(entry.filters) do names[#names + 1] = filter end
    for _, option in ipairs(entry.options) do names[#names + 1] = option end
    print(name .. '\\t' .. entry.replaces .. '\\t' .. table.concat(names, ','))
end
''' % FIELDS


def declarations() -> list[tuple[str, str, set[str]]]:
    result = subprocess.run(['lua5.1', '-'], input=DUMP,
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f'could not read the data page:\n{result.stderr}')

    entries = []
    for line in result.stdout.strip().splitlines():
        name, replaces, names = line.split('\t')
        entries.append((name, replaces, set(names.split(','))))
    return entries


def template_parameters(title: str) -> set[str]:
    """The parameters a template actually reads, from its wikitext."""
    result = subprocess.run(
        ['docker', 'compose', '-f', COMPOSE_FILE, 'exec', '-T', 'mediawiki',
         'php', 'maintenance/getText.php', title],
        capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(
            f'{title} is not on the local wiki - seed it first:\n'
            '  uv run python infra/football_queries/compare_rendered_blocks.py'
            ' --seed')

    # Only the transcluded half: the documentation after </includeonly> shows
    # example calls, and their parameters are prose, not an interface.
    body = result.stdout.split('</includeonly>')[0]
    return set(re.findall(r'\{\{\{([^{}|<>]+?)[|}]', body))


def main() -> None:
    # A checker that has never reported anything is not evidence that there is
    # nothing to report, so it is asked to find a mismatch that is put there.
    selftest = '--selftest' in sys.argv

    mismatches = 0
    for name, replaces, declared in sorted(declarations()):
        actual = template_parameters(replaces)
        if selftest:
            declared = (declared - {sorted(actual & declared)[0]}) | {'פדיחה'}
        missing = actual - declared - set(EXPECTED_ABSENT)
        extra = declared - actual

        print(f'{name}  <-  {replaces}')
        if not missing and not extra:
            print(f'  ok, {len(declared)} parameter(s) match')
            continue

        mismatches += len(missing) + len(extra)
        for parameter in sorted(missing):
            print(f'  MISSING  {parameter} - the template takes it, '
                  f'{name} refuses it')
        for parameter in sorted(extra):
            print(f'  EXTRA    {parameter} - {name} answers it, '
                  'the template cannot be asked it')

    print(f'\n{mismatches} mismatch(es)')

    if selftest:
        # One dropped and one invented parameter per entry point.
        expected = 2 * len(declarations())
        if mismatches == expected:
            print('SELFTEST PASSED: the checker reports both directions')
            sys.exit(0)
        print(f'SELFTEST FAILED: expected {expected} - this checker is not '
              'evidence')
        sys.exit(1)

    sys.exit(min(mismatches, 100))


if __name__ == '__main__':
    main()
