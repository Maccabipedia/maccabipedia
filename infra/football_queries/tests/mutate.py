"""Mutation harness: every mutation here must turn the Lua suites red.

A suite that has never failed is not evidence. An earlier version of these
modules survived 10 of 18 mutations green, each one a wrong number on a live
page. Run this after touching the modules:

    uv run python infra/football_queries/tests/mutate.py

A SURVIVED line means that code path has no test. Exit code is the number of
survivors, so CI can gate on it.
"""
import subprocess
import sys
from pathlib import Path

LOGIC = Path('infra/football_queries/Module_FootballQueries.lua')
FIELDS = Path('infra/football_queries/Module_FootballQueries_Fields.lua')
SUITES = [
    'infra/football_queries/tests/test_football_queries.lua',
    'infra/football_queries/tests/test_coverage_gaps.lua',
    'infra/football_queries/tests/test_aggregate.lua',
    # Omitted once, which let three mutations in the renderer survive unseen.
    'infra/football_queries/tests/test_player_events.lua',
]
PLAYER_EVENTS = Path('infra/football_queries/Module_FootballPlayerEvents.lua')
BLOCKS = Path('infra/football_queries/Module_FootballStatsBlocks.lua')

# (label, file, find, replace). `find` must appear exactly once, or the harness
# says so instead of silently mutating the wrong place - which is how a broken
# mutation once reported a false survivor.
MUTATIONS = [
    ('quote rule falls back to strip', LOGIC,
     'local rule = Fields.columns[column]',
     'local rule = Fields.columns[column] or "strip"'),
    ('row-limit guard >= to >', LOGIC,
     'if #rows >= options.limit then', 'if #rows > options.limit then'),
    ('maxLimit guard disabled', LOGIC,
     'if options.limit > Fields.maxLimit then', 'if false then'),
    ('empty IN guard disabled', LOGIC, 'if #literals == 0 then', 'if false then'),
    ('rounding truncates', LOGIC,
     'math.floor(value + 0.5)', 'math.floor(value)'),
    ('numberNotEqual becomes equal', LOGIC,
     "addComparison(spec.column, '!=', value)",
     "addComparison(spec.column, '=', value)"),
    ('Team default flipped to 0', LOGIC,
     "builder:addComparison('Games_Events.Team', '=', 1)",
     "builder:addComparison('Games_Events.Team', '=', 0)"),
    ('Team default removed', LOGIC,
     'if builder.tables.Games_Events and not builder.teamConstrained\n'
     '\t\t\tand not skipDefaults then',
     'if false then'),
    ('backslash escape removed', LOGIC,
     """value:gsub('\\\\', '\\\\\\\\'):gsub('"', '\\\\"')""",
     """value:gsub('"', '\\\\"')"""),
    ('double-quote escape removed', LOGIC,
     """:gsub('"', '\\\\"')""", ''),
    ('positional key check removed', LOGIC,
     "if type(name) ~= 'string' then", 'if false then'),
    ('date format unquoting removed', LOGIC,
     """format = format:gsub('^"(.*)"$', '%1'):gsub("^'(.*)'$", '%1')""",
     'format = format'),
    ('sort removed', LOGIC, 'table.sort(names)', ''),
    ('entity table loses &quot;', LOGIC, """['&quot;'] = '"',""", ''),
    ('entity table loses &#39;', LOGIC, """['&#39;'] = "'",""", ''),
    ('entity table loses the hex quote', LOGIC,
     """['&#x22;'] = '"',""", ''),
    # Cargo decodes entities in the WHERE after this module escapes it, so this
    # guard is the only thing standing between a crafted parameter and the
    # unfiltered total. It was missing entirely until the arbitration.
    ('surviving-ampersand guard removed', LOGIC,
     "if value:find('&', 1, true) then", 'if false then'),
    ('aggregate whitelist bypassed', LOGIC,
     'aggregate = Fields.aggregates[mw.text.trim(requested)]',
     'aggregate = mw.text.trim(requested)'),
    ('PlayerName keep to strip', FIELDS,
     "['Games_Events.PlayerName'] = 'keep'",
     "['Games_Events.PlayerName'] = 'strip'"),
    ('Opponent strip to keep', FIELDS,
     "['Football_Games.Opponent'] = 'strip'",
     "['Football_Games.Opponent'] = 'keep'"),
    ('Competition keep to strip', FIELDS,
     "['Football_Games.Competition'] = 'keep'",
     "['Football_Games.Competition'] = 'strip'"),
    ('תיקו and הפסד swapped', FIELDS, "['תיקו'] = 2,", "['תיקו'] = 3,"),
    ('גביע repointed to League', FIELDS,
     "['גביע'] = 'Competitions.Trophy = 1'",
     "['גביע'] = 'Competitions.League = 1'"),
    ('בינלאומי repointed', FIELDS,
     "['בינלאומי'] = 'Competitions.International = 1'",
     "['בינלאומי'] = 'Competitions.League = 1'"),
    ('רשמי repointed', FIELDS,
     "['רשמי'] = 'Competitions.Official = 1'",
     "['רשמי'] = 'Competitions.League = 1'"),
    ('תת אירוע repointed to EventType', FIELDS,
     "['תת אירוע'] = { column = 'Games_Events.SubType'",
     "['תת אירוע'] = { column = 'Games_Events.EventType'"),
    ('תוצאה מכבי repointed to opponent', FIELDS,
     "['תוצאה מכבי'] = { column = 'Football_Games.ResultMaccabi'",
     "['תוצאה מכבי'] = { column = 'Football_Games.ResultOpponent'"),
    ('אצטדיונים repointed to Opponent', FIELDS,
     "['אצטדיונים'] = { column = 'Football_Games.Stadium'",
     "['אצטדיונים'] = { column = 'Football_Games.Opponent'"),
    ('opponent alias matchQuotes to strip', FIELDS,
     "matchQuotes = 'keep'", "matchQuotes = 'strip'"),
    ('opponent alias matchColumn to CanonicalName', FIELDS,
     "matchColumn = 'o1.OriginalName'", "matchColumn = 'o1.CanonicalName'"),
    ('opponent alias returnColumn to CanonicalName', FIELDS,
     "returnColumn = 'o2.OriginalName'", "returnColumn = 'o2.CanonicalName'"),
    ('stadium alias s1 to s2', FIELDS,
     "matchColumn = 's1.CanonicalName'", "matchColumn = 's2.CanonicalName'"),
    # `returnQuotes` was deleted, not tested: the games column's own quote rule
    # already governs the returned names, so the knob had no observable effect
    # and a mutation of it could never be killed. Dead configuration that can
    # disagree with `columns` is worse than no configuration.
    ('HOLDS becomes equals', LOGIC,
     "'%s HOLDS %s', spec.column", "'%s = %s', spec.column"),
    # The merge. Each of these is a plausible-looking wrong number in a block.
    ('merge derives joins from the shared filters only', LOGIC,
     'local unionBuilder = buildInto(union)',
     'local unionBuilder = buildInto(shared)'),
    ('merge puts cell conditions in the WHERE too', LOGIC,
     'local sharedBuilder = buildInto(shared, true)',
     'local sharedBuilder = buildInto(union, true)'),
    ('game grain counts rows instead of distinct games', LOGIC,
     "if grain == 'game' then", 'if false then'),
    ('grain validation removed', LOGIC,
     "if grain ~= 'event' and grain ~= 'game' then", 'if false then'),
    ('cell conditions dropped from the aggregate', LOGIC,
     "for _, condition in ipairs(cellBuilder.conditions) do",
     "for _, condition in ipairs({}) do"),
    ('cell values no longer default to zero', LOGIC,
     "values[entry.name] = tonumber(rows[1][entry.alias]) or 0",
     "values[entry.name] = tonumber(rows[1][entry.alias])"),
    ('duplicate cell names allowed', LOGIC,
     'if seen[cell.name] then', 'if false then'),
    ('HOLDS in a cell allowed through', LOGIC,
     "if condition:find(' HOLDS ', 1, true) then", 'if false then'),
    ('grain defaults to event again', LOGIC,
     "if grain ~= 'event' and grain ~= 'game' then",
     "if grain ~= nil and grain ~= 'event' and grain ~= 'game' then"),
    # The four a review found surviving. Each is a wrong number on a page.
    ('Team default gated on shared instead of the union', LOGIC,
     'local teamDefaultNeeded = unionBuilder.tables.Games_Events',
     'local teamDefaultNeeded = sharedBuilder.tables.Games_Events'),
    ('Team default moved back into the WHERE', LOGIC,
     "if teamDefaultNeeded and grain == 'event'",
     "if false and grain == 'event'"),
    ('modifiers read from the cell alone', LOGIC,
     'local cellBuilder = buildInto(cell.filters or {}, true, union)',
     'local cellBuilder = buildInto(cell.filters or {}, true)'),
    # Renderer and block data.
    ('prime uses one constant category for every tab', PLAYER_EVENTS,
     "filters['קטגוריית מפעל'] = tab", "filters['קטגוריית מפעל'] = 'ליגה'"),
    ('materialise returns the proxy uncopied', PLAYER_EVENTS,
     'local function materialise(value)\n\tif type(value) ~= \'table\' then\n'
     '\t\treturn value\n\tend',
     'local function materialise(value)\n\tif true then\n\t\treturn value\n\tend'),
    ('the rounding epsilon is removed', PLAYER_EVENTS,
     'math.floor(value * 100 + 0.5 + 1e-9)', 'math.floor(value * 100 + 0.5)'),
    ('the zero-denominator guard is removed', PLAYER_EVENTS,
     'if appearances ~= 0 then', 'if true then'),
    ('a missing cell defaults to zero again', PLAYER_EVENTS,
     'if value == nil then', 'if false then'),
    ('tab renders empty instead of raising', PLAYER_EVENTS,
     "if not value or mw.text.trim(value) == '' then", 'if false then'),
    ('variables lose the entity from their name', PLAYER_EVENTS,
     "return string.format('%s/%s/%s', VAR_PREFIX, entity, tab)",
     "return string.format('%s/%s', VAR_PREFIX, tab)"),
    ('a block cell loses its subtype filter', BLOCKS,
     "['מספר אירוע'] = '3', ['תת אירוע'] = '35'", "['מספר אירוע'] = '3'"),
]


def suites_pass() -> bool:
    for suite in SUITES:
        result = subprocess.run(['lua5.1', suite], capture_output=True)
        if result.returncode != 0:
            return False
    return True


def main() -> None:
    if not suites_pass():
        sys.exit('the suites fail before any mutation - fix that first')

    killed, survived, broken = 0, [], []

    for label, path, find, replace in MUTATIONS:
        original = path.read_text(encoding='utf-8')
        occurrences = original.count(find)
        if occurrences != 1:
            broken.append(f'{label} (pattern found {occurrences} times)')
            print(f'  BROKEN MUTATION  {label}: pattern appears {occurrences}x')
            continue

        path.write_text(original.replace(find, replace), encoding='utf-8')
        try:
            if suites_pass():
                survived.append(label)
                print(f'  SURVIVED  {label}')
            else:
                killed += 1
                print(f'  killed    {label}')
        finally:
            path.write_text(original, encoding='utf-8')

    print(f'\nkilled {killed}, survived {len(survived)}, '
          f'broken patterns {len(broken)}')
    for label in survived:
        print(f'  UNTESTED PATH: {label}')
    if broken:
        print('a broken pattern proves nothing - fix the harness')
    sys.exit(len(survived) + len(broken))


if __name__ == '__main__':
    main()
