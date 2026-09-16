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
    'infra/football_queries/tests/test_stats_block.lua',
]
RENDERER = Path('infra/football_queries/Module_FootballStatsBlock.lua')
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
    ('Team default flipped to the opponent', LOGIC,
     "builder:addComparison(Fields.roles.sideColumn, '=', Fields.sides.maccabi)",
     "builder:addComparison(Fields.roles.sideColumn, '=', Fields.sides.opponent)"),
    ('Team default removed', LOGIC,
     'if builder.tables[Fields.roles.events] and not builder.teamConstrained\n'
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
    ('the probe stops declaring its grain', LOGIC,
     "\t\t\tgrain = 'event',\n\t\t\tfilters = { ['מספר אירוע'] = eventType:gsub(';', ',') },",
     "\t\t\tfilters = { ['מספר אירוע'] = eventType:gsub(';', ',') },"),
    ('the probe counts games instead of events', LOGIC,
     "\t\t\tgrain = 'event',\n\t\t\tfilters = { ['מספר אירוע'] = eventType:gsub(';', ',') },",
     "\t\t\tgrain = 'game',\n\t\t\tfilters = { ['מספר אירוע'] = eventType:gsub(';', ',') },"),
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
    ('the no-rows guard is removed', LOGIC,
     'if not rows[1] then', 'if false then'),
    ('ליגה repointed to Trophy', FIELDS,
     "['ליגה'] = 'Competitions.League = 1',",
     "['ליגה'] = 'Competitions.Trophy = 1',"),
    ('יתר-רשמיים loses its exclusions', FIELDS,
     """['יתר-רשמיים'] = '(Competitions.Official = 1 AND Competitions.League = 0'""",
     """['יתר-רשמיים'] = '(Competitions.Official = 1 AND Competitions.League >= 0'"""),
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
    ('a stored entity passes through the alias expansion', LOGIC,
     "if tostring(row.name):find('&', 1, true) then", 'if false then'),
    ('stadium alias s1 to s2', FIELDS,
     "matchColumn = 's1.CanonicalName'", "matchColumn = 's2.CanonicalName'"),
    # `returnQuotes` was deleted, not tested: the games column's own quote rule
    # already governs the returned names, so the knob had no observable effect
    # and a mutation of it could never be killed. Dead configuration that can
    # disagree with `columns` is worse than no configuration.
    # Sport facts read from the schema, so a second sport is a data page and
    # not an edit to shared code.
    ('base table hardcoded again', LOGIC,
     'local tableNames = { Fields.baseTable }',
     "local tableNames = { 'Football_Games' }"),
    ('side value hardcoded again', LOGIC,
     "builder:addComparison(Fields.roles.sideColumn, '=', Fields.sides.maccabi)",
     "builder:addComparison('Games_Events.Team', '=', 1)"),
    ('opponent side value flipped', FIELDS, 'opponent = 0,', 'opponent = 1,'),
    ('maccabi side value flipped', FIELDS, 'maccabi = 1,', 'maccabi = 0,'),
    ('events role repointed', FIELDS,
     "events = 'Games_Events',", "events = 'Games_Referees',"),
    # Per-entry-point filter sets.
    ('entry point filter list ignored', LOGIC,
     'if allowedFilters and not allowedFilters[name]',
     'if false and not allowedFilters[name]'),
    ('entry point option list ignored', LOGIC,
     'if allowedOptions and not allowedOptions[name] then',
     'if false then'),
    ('shim stops declaring its entry point', LOGIC,
     'return separate(frame:getParent().args, entryPoint)',
     'return separate(frame:getParent().args)'),
    ('the shims swap entry points', LOGIC,
     "parentArgumentsOf(frame, 'playerEventCount')",
     "parentArgumentsOf(frame, 'gameDataCount')"),
    ('a shim stops refusing arguments of its own', LOGIC,
     'for _ in pairs(frame.args) do\n\t\terror(string.format(',
     'for _ in pairs({}) do\n\t\terror(string.format('),
    ('the player shim loses a filter its template takes', FIELDS,
     "'שופט', 'שחקן', 'תוצאה', 'תוצאה יריבה', 'תוצאה מכבי',",
     "'שופט', 'תוצאה', 'תוצאה יריבה', 'תוצאה מכבי',"),
    ('a filter the template lacks is added to the shim', FIELDS,
     "'עונה', 'פורמט תאריך', 'קטגוריית מפעל', 'שופט', 'תאריך',",
     "'עונה', 'פורמט תאריך', 'קטגוריית מפעל', 'שופט', 'תאריך', 'שחקן',"),
    # A reviewer added 15 mutations of its own and 8 survived. These are those
    # paths, each one a wrong number nothing was watching.
    ('side constraint restricted to event grain again', LOGIC,
     "if teamDefaultNeeded and not cellBuilder.teamConstrained\n"
     "\t\t\t\tand cellBuilder.tables[Fields.roles.events] then",
     "if teamDefaultNeeded and grain == 'event'\n"
     "\t\t\t\tand not cellBuilder.teamConstrained then"),
    ('modifier scope widened back to the union', LOGIC,
     'local cellBuilder = buildInto(cell.filters or {}, true, modifiers)',
     'local cellBuilder = buildInto(cell.filters or {}, true, union)'),
    ('side column role bypassed', LOGIC,
     "Fields.roles.sideColumn, Fields.sides.maccabi)",
     "'Games_Events.Team', Fields.sides.maccabi)"),
    ('date format filter dropped from the shim list', FIELDS,
     "'עונה', 'פורמט תאריך', 'קטגוריית מפעל', 'שופט', 'תאריך',",
     "'עונה', 'קטגוריית מפעל', 'שופט', 'תאריך',"),
    ('date filter dropped from the shim list', FIELDS,
     "'עונה', 'פורמט תאריך', 'קטגוריית מפעל', 'שופט', 'תאריך',",
     "'עונה', 'פורמט תאריך', 'קטגוריית מפעל', 'שופט',"),
    ('limit no longer reaches the query', LOGIC,
     'limit = options.limit or 2,', 'limit = 2,'),
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
     'if value == nil and not entry.sums then', 'if false then'),
    ('an empty sum defaults to zero like a count', LOGIC,
     'if value == nil and not entry.sums then', 'if value == nil then'),
    ('duplicate cell names allowed', LOGIC,
     'if seen[cell.name] then', 'if false then'),
    ('HOLDS in a cell allowed through', LOGIC,
     "if condition:find(' HOLDS ', 1, true) then", 'if false then'),
    ('grain defaults to event again', LOGIC,
     "if grain ~= 'event' and grain ~= 'game' then",
     "if grain ~= nil and grain ~= 'event' and grain ~= 'game' then"),
    # The four a review found surviving. Each is a wrong number on a page.
    ('Team default gated on shared instead of the union', LOGIC,
     'local teamDefaultNeeded = unionBuilder.tables[Fields.roles.events]',
     'local teamDefaultNeeded = sharedBuilder.tables[Fields.roles.events]'),
    ('side constraint removed from the cells', LOGIC,
     'if teamDefaultNeeded and not cellBuilder.teamConstrained',
     'if false and not cellBuilder.teamConstrained'),
    ('modifiers read from the cell alone', LOGIC,
     'local cellBuilder = buildInto(cell.filters or {}, true, modifiers)',
     'local cellBuilder = buildInto(cell.filters or {}, true)'),
    # Renderer and block data.
    ('prime uses one constant category for every tab', RENDERER,
     "filters['קטגוריית מפעל'] = tab", "filters['קטגוריית מפעל'] = 'ליגה'"),
    ('materialise returns the proxy uncopied', RENDERER,
     'local function materialise(value)\n\tif type(value) ~= \'table\' then\n'
     '\t\treturn value\n\tend',
     'local function materialise(value)\n\tif true then\n\t\treturn value\n\tend'),
    ('the rounding epsilon is removed', RENDERER,
     'math.floor(value * 100 + 0.5 + 1e-9)',
     'math.floor(value * 100 + 0.5)'),
    ('the rounding epsilon is coarsened to 1e-3', RENDERER,
     'math.floor(value * 100 + 0.5 + 1e-9)',
     'math.floor(value * 100 + 0.5 + 1e-3)'),
    ('the negative-ratio guard is removed', RENDERER,
     '\tif value < 0 then\n\t\terror(string.format(',
     '\tif false then\n\t\terror(string.format('),
    ('the zero-denominator guard is removed', RENDERER,
     'if appearances ~= 0 then', 'if true then'),
    ('a missing cell defaults to zero again', RENDERER,
     'local value = cells[name]\n\tif value == nil then',
     'local value = cells[name]\n\tif false then'),
    ('tab renders empty instead of raising', RENDERER,
     "if not value or mw.text.trim(value) == '' then", 'if false then'),
    ('value stops checking the cell is declared', RENDERER,
     'if not declared then', 'if false then'),
    ('value reports an unprimed page as empty', RENDERER,
     "if not primed or mw.text.trim(primed) == '' then", 'if false then'),
    ('a cell value is stashed as 0 instead of empty', RENDERER,
     'local function valueText(value)\n\tif value == nil then',
     'local function valueText(value)\n\tif false then'),
    ('cell variables lose the tab from their name', RENDERER,
     "return variableName(blockName, entity, tab) .. '/' .. cell",
     "return variableName(blockName, entity, '') .. '/' .. cell"),
    ('variables lose the entity from their name', RENDERER,
     "return string.format('%s/%s/%s/%s', VAR_PREFIX, blockName, entity, tab)",
     "return string.format('%s/%s/%s', VAR_PREFIX, blockName, tab)"),
    ('a block cell loses its subtype filter', BLOCKS,
     "['מספר אירוע'] = '3', ['תת אירוע'] = '35'", "['מספר אירוע'] = '3'"),
    # The summing path: a sum that becomes a count is a plausible number on
    # every calendar page, and the day block has 366 of them.
    ('a summing cell counts rows instead', LOGIC,
     'if cell.sum then', 'if false then'),
    ('goals for and against are summed from the same column', FIELDS,
     "['ספיגות'] = 'Football_Games.ResultOpponent',",
     "['ספיגות'] = 'Football_Games.ResultMaccabi',"),
    ('a summing cell may join the events table', LOGIC,
     'if unionBuilder.tables[Fields.roles.events] then',
     'if false then'),
    ('a summing cell may be event grain', LOGIC,
     "if grain ~= 'game' then", 'if false then'),
    ('an unmatched sum falls back to zero', LOGIC,
     "'SUM(CASE WHEN %s THEN %s ELSE NULL END)=%s'",
     "'SUM(CASE WHEN %s THEN %s ELSE 0 END)=%s'"),
    ('a NULL count comes back as zero again', LOGIC,
     'return tonumber(rows[1] and rows[1].n)',
     'return tonumber(rows[1] and rows[1].n) or 0'),
    ('the shim prints zero for a NULL sum', LOGIC,
     '\tif value == nil then\n\t\treturn \'\'\n\tend\n\n\t-- The template rounds',
     '\tif false then\n\t\treturn \'\'\n\tend\n\n\t-- The template rounds'),
    ('a row may name a cell the block does not produce', RENDERER,
     'if row.cell and not declared[row.cell] then', 'if false then'),
    ('the sum ignores its own cell filter', LOGIC,
     "'SUM(CASE WHEN %s THEN %s ELSE NULL END)=%s',\n\t\t\t\tcondition, column, alias",
     "'SUM(CASE WHEN 1=1 THEN %s ELSE NULL END)=%s',\n\t\t\t\tcolumn, alias"),
    # The block's own constant filters. Dropping this one silently narrows the
    # day block from "this day in any year" to one single date.
    ('the day block gets the default date format', BLOCKS,
     '''filters = { ['פורמט תאריך'] = '"%d-%m"' },''',
     '''filters = { ['פורמט תאריך'] = '"%d-%m-%Y"' },'''),
    ('the day block loses its date format', BLOCKS,
     "filters = { ['פורמט תאריך'] = '\"%d-%m\"' },", ''),
    ('block constants never reach the query', RENDERER,
     'for name, value in pairs(block.filters or {}) do',
     'for name, value in pairs({}) do'),
    ('a caller may override a block constant', RENDERER,
     "if shared[name] ~= nil and mw.text.trim(tostring(shared[name])) ~= '' then",
     'if false then'),
    ('an empty summed cell renders zero', RENDERER,
     'formatters.plainOrEmpty = function(cells, row)\n\tlocal value = cells[row.cell]',
     'formatters.plainOrEmpty = function(cells, row)\n\tlocal value = cells[row.cell] or 0'),
    # render: the whole widget from one query. Every one of these is a wrong
    # number or a broken widget on 366 calendar pages.
    ('a tab reads another tab\'s cells', RENDERER,
     "tabCells[cell.name] = values[tab .. '/' .. cell.name]",
     'tabCells[cell.name] = values[cell.name]'),
    ('the panels lose their separator', RENDERER,
     "#parts == 0 and '' or '|-|'", "''"),
    ('the heading shows the label instead', RENDERER,
     'string.format(heading.format, entry.heading,',
     'string.format(heading.format, entry.label,'),
    ('the heading counts wins instead of games', RENDERER,
     'valueText(tabCells[heading.cell])', "valueText(tabCells['wins'])"),
    ('the heading may name a cell the block lacks', RENDERER,
     'if not declared[heading.cell] then', 'if false then'),
    ('a label may carry a tabber separator', RENDERER,
     "if entry.label:find('=', 1, true) or entry.label:find('|', 1, true) then",
     'if false then'),
    ('render accepts a block with no tab strip', RENDERER,
     'if not declaration.tabStrip then', 'if false then'),
    ('the skin loses the wrapper it scopes the tabs to', RENDERER,
     '\'<div class="tabber-converted">\'', "'<div>'"),
    ('the first tab shows the officials category', BLOCKS,
     "{ category = 'ליגה', label = 'ליגה', heading = 'ליגה' },",
     "{ category = 'רשמי', label = 'ליגה', heading = 'ליגה' },"),
    ('the cup tab is headed by its label', BLOCKS,
     "heading = 'גביע המדינה'", "heading = 'גביע'"),
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
