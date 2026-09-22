"""Mutation harness: every mutation here must turn the Lua suites red.

A suite that has never failed is not evidence. An earlier version of these
modules survived 10 of 18 mutations green, each one a wrong number on a live
page. Run this after touching the modules:

    uv run python infra/lua_modules/tests/mutate.py

A SURVIVED line means that code path has no test. Exit code is the number of
survivors, so CI can gate on it.
"""
import subprocess
import sys
from pathlib import Path

LOGIC = Path('infra/lua_modules/Module_SportQueries.lua')
QUERIES_SHIM = Path('infra/lua_modules/Module_FootballQueries.lua')
FIELDS = Path('infra/lua_modules/Module_FootballQueries_Fields.lua')
SUITES = [
    'infra/lua_modules/tests/test_football_queries.lua',
    'infra/lua_modules/tests/test_coverage_gaps.lua',
    'infra/lua_modules/tests/test_aggregate.lua',
    # Omitted once, which let three mutations in the renderer survive unseen.
    'infra/lua_modules/tests/test_stats_block.lua',
    'infra/lua_modules/tests/test_leaderboard.lua',
    'infra/lua_modules/tests/test_season_squad.lua',
    'infra/lua_modules/tests/test_season_table.lua',
    'infra/lua_modules/tests/test_player_stats.lua',
    'infra/lua_modules/tests/test_date.lua',
    'infra/lua_modules/tests/test_season_trophies.lua',
    'infra/lua_modules/tests/test_perplayer_schema.lua',
]
RENDERER = Path('infra/lua_modules/Module_StatsBlock.lua')
BLOCK_SHIM = Path('infra/lua_modules/Module_FootballStatsBlock.lua')
BLOCKS = Path('infra/lua_modules/Module_FootballStatsBlocks.lua')
SQUAD = Path('infra/lua_modules/Module_FootballSeasonSquad.lua')
SEASON_TABLE = Path('infra/lua_modules/Module_FootballSeasonTable.lua')
PLAYER_STATS = Path('infra/lua_modules/Module_FootballPlayerStats.lua')
DATE = Path('infra/lua_modules/Module_FootballDate.lua')
TROPHIES = Path('infra/lua_modules/Module_SeasonTrophies.lua')

# The end of the season block's tab strip up to its first box - the only
# place where a בינלאומי tab is followed by the appearances box, so a
# mutation anchored on it matches the season block and nothing else.
SEASON_TAB_TAIL = (
    "\t\t\t{ category = 'בינלאומי', label = 'בינלאומי', heading = 'בינלאומי' },\n"
    "\t\t},\n"
    "\t\ttabHeading = '<div class=\"tab-header\">%s (%s %s)</div>',\n\n"
    "\t\tboxes = {\n\t\t\t{ key = 'appearances', title = 'שיאני הופעות',")

# (label, file, find, replace). `find` must appear exactly once, or the harness
# says so instead of silently mutating the wrong place - which is how a broken
# mutation once reported a false survivor.
MUTATIONS = [
    # The generalisations basketball needs (test_perplayer_schema.lua and the
    # hoops block in test_leaderboard.lua), and the football schema keys behind them.
    ('grain: a table without one is accepted', LOGIC,
     "if grain ~= 'game' and grain ~= 'perPlayer' then", 'if false then'),
    ('grain: two multiplying tables accepted', LOGIC, 'if #names > 1 then', 'if #names > 2 then'),
    ('grain: the summed column is not joined', LOGIC,
     '\t\t\t\tunionBuilder:needs(column)\n', ''),
    ('grain: a sum over the per-player table gets no side constraint', LOGIC,
     '\t\t\t\tcellBuilder:needs(sumColumnOf[cell])\n', ''),
    ('grain: a per-player sum accepted as game grain', LOGIC,
     "if columnGrain == 'perPlayer' and grain ~= 'event' then", 'if false then'),
    ('grain: a game-column sum accepted with a multiplying join', LOGIC,
     "if columnGrain == 'game' and multiplying then", 'if false then'),
    ('grain: an event count without a multiplying table accepted', LOGIC,
     '\t\t\t\tif not multiplying then', '\t\t\t\tif false then'),
    ('choice: an empty condition is added anyway', LOGIC,
     "\t\tif condition ~= '' then\n\t\t\tbuilder:add(condition)", '\t\tif true then\n\t\t\tbuilder:add(condition)'),
    ('choice: its tables are not joined', LOGIC,
     'for _, tableName in ipairs(spec.tables or {}) do', 'for _, tableName in ipairs({}) do'),
    ('list: the prefix is kept', LOGIC, 'if spec.stripPrefix then', 'if false then'),
    ('narrow: the filter comes from nowhere', LOGIC,
     'if narrowFilter and narrowed[narrowFilter] == nil then', 'if false then'),
    ('side: the layer asks for the opponent', LOGIC,
     'narrowed[sideFilter] = Fields.sides.maccabiValue', 'narrowed[sideFilter] = Fields.sides.opponentValue'),
    ('side: no side filter, no narrowing', LOGIC,
     'if sideFilter and narrowed[sideFilter] == nil then', 'if false then'),
    ('rank: keepZero ignored', LOGIC, 'if entry.count > 0 or keepZero then', 'if entry.count > 0 then'),
    ('rank: zeroes always kept', LOGIC, 'if entry.count > 0 or keepZero then', 'if true then'),
    ('renderer: a summing box counts', RENDERER, '\t\t\t\t\tsum = box.sum,\n', ''),
    ('renderer: keepZero not passed on', RENDERER, 'keepZero = declaration.keepZero', 'keepZero = nil'),
    ('renderer: emptyText never printed', RENDERER,
     'if #result.rows == 0 and declaration.emptyText then', 'if false then'),
    ('renderer: a more link on a summing box', RENDERER,
     "if box.sum and (declaration.moreText or '') ~= '' then", 'if false then'),
    ('schema: the events table declared game-grain', FIELDS,
     "\t\t\tjoin = 'Football_Games._pageID = Games_Events._pageID',\n\t\t\tgrain = 'perPlayer',",
     "\t\t\tjoin = 'Football_Games._pageID = Games_Events._pageID',\n\t\t\tgrain = 'game',"),
    ('schema: no side filter declared', FIELDS, "\t\tsideFilter = 'מכבי',\n", ''),
    ('schema: no narrow filter declared', FIELDS, "\t\tnarrowFilter = 'מספר אירוע',\n", ''),
    ('schema: the layer asks for the opponent by default', FIELDS,
     "maccabiValue = 'כן',", "maccabiValue = 'לא',"),
    # The football shims - the one line each that decides which sport answers.
    ('queries shim: bound to the wrong schema page', QUERIES_SHIM,
     "mw.loadData('Module:FootballQueries/Fields')", "mw.loadData('Module:FootballStatsBlocks')"),
    ('block shim: bound to the wrong block data', BLOCK_SHIM,
     "mw.loadData('Module:FootballStatsBlocks')", "mw.loadData('Module:FootballQueries/Fields')"),
    ('block shim: a different variable and error prefix', BLOCK_SHIM,
     "'FootballStatsBlock')", "'StatsBlock')"),
    ('shared logic: the error prefix ignores the schema name', LOGIC,
     '\tlocal NAME = Fields.name', "\tlocal NAME = 'SportQueries'"),
    # Module:SeasonTrophies - each sport's tables, the order, the guards, the cache.
    ('trophies: football reads the basketball tables', TROPHIES,
     "['כדורגל'] = { achievements = 'Achievements', competitions = 'Competitions' }",
     "['כדורגל'] = { achievements = 'Basketball_Achievements', competitions = 'Basketball_Competitions' }"),
    ('trophies: volleyball reads the basketball tables', TROPHIES,
     "['כדורעף'] = { achievements = 'Volleyball_Achievements', competitions = 'Volleyball_Competitions',",
     "['כדורעף'] = { achievements = 'Basketball_Achievements', competitions = 'Basketball_Competitions',"),
    ('trophies: the volleyball exclusion dropped', TROPHIES,
     "\t\texcluded = { 'הליגה הארצית' } },", '\t\t},'),
    ('trophies: runners-up counted as wins', TROPHIES,
     'a.Achievement="זכיה"', 'a.Achievement!="זכיה"'),
    ('trophies: unofficial competitions counted', TROPHIES,
     "local where = 'c.Official AND ", "local where = '"),
    ('trophies: the join dropped', TROPHIES,
     "join = 'a.Competition=c.OriginalName'", "join = ''"),
    ('trophies: storage order instead of by competition', TROPHIES,
     "orderBy = 'a.Competition'", "orderBy = 'a.Season'"),
    ('trophies: one space between competitions', TROPHIES,
     "local SEPARATOR = ',  '", "local SEPARATOR = ', '"),
    ('trophies: only the last win of a season kept', TROPHIES,
     'lists[season] = lists[season] .. SEPARATOR .. row.competition',
     'lists[season] = row.competition'),
    ('trophies: a truncated result passes as a short answer', TROPHIES,
     'if #rows >= ROW_LIMIT then', 'if false then'),
    ("trophies: Cargo's silent default limit", TROPHIES,
     'local ROW_LIMIT = 500', 'local ROW_LIMIT = 100'),
    ('trophies: an unknown sport returns nothing', TROPHIES,
     'if SPORTS[sport] == nil then', 'if false then'),
    ('trophies: every season queries again', TROPHIES,
     "if stored(frame, marker) == '' then", 'if true then'),
    ('trophies: the sports share one list', TROPHIES,
     "'SeasonTrophies|' .. sport .. '|' .. season", "'SeasonTrophies|' .. season"),
    # Module:FootballPlayerStats - each number's semantics, the cache, the name.
    ('player stats: games cells count event rows', PLAYER_STATS, "if cell.grain == 'games' then", 'if false then'),
    ('player stats: games not distinct', PLAYER_STATS, "'COUNT(DISTINCT CASE WHEN '", "'COUNT(CASE WHEN '"),
    ('player stats: own goals counted', PLAYER_STATS, ' AND Games_Events.SubType != 33', ''),
    ('player stats: reds lose the straight red', PLAYER_STATS, 'SubType IN (72, 73)', 'SubType IN (72)'),
    ('player stats: clean sheets on one conceded', PLAYER_STATS,
     'Football_Games.ResultOpponent = 0', 'Football_Games.ResultOpponent = 1'),
    ('player stats: the cup tab reads the league', PLAYER_STATS,
     "['גביע'] = 'Competitions.Trophy = 1'", "['גביע'] = 'Competitions.League = 1'"),
    ('player stats: opponents\' events counted', PLAYER_STATS,
     "' AND Games_Events.Team = 1',", "'',"),
    ('player stats: an empty count prints empty', PLAYER_STATS,
     "whole(row['c' .. categoryIndex .. '_' .. cellIndex], '0'))", "whole(row['c' .. categoryIndex .. '_' .. cellIndex], ''))"),
    ('player stats: conceded over nothing prints 0', PLAYER_STATS,
     "whole(concededRow['c' .. categoryIndex], '')", "whole(concededRow['c' .. categoryIndex], '0')"),
    ('player stats: penalties conceded over nothing prints empty', PLAYER_STATS,
     "whole(penaltyRow['c' .. categoryIndex], '0')", "whole(penaltyRow['c' .. categoryIndex], '')"),
    ('player stats: technical games conceded', PLAYER_STATS,
     "' AND Games_Events.EventType IN (1, 5) AND Football_Games.Technical = -1',",
     "' AND Games_Events.EventType IN (1, 5)',"),
    ('player stats: the keeper\'s own penalties', PLAYER_STATS, 'ge2.Team = 0', 'ge2.Team = 1'),
    ('player stats: every call queries again', PLAYER_STATS, "if stored(frame, marker) == '' then", 'if true then'),
    ('player stats: players share numbers', PLAYER_STATS,
     "'FootballPlayerStats|' .. player .. '|'", "'FootballPlayerStats|' .. '|'"),
    ('player stats: any row count accepted', PLAYER_STATS, 'if #rows ~= 1 then', 'if false then'),
    ('player stats: the ampersand guard removed', PLAYER_STATS, "if name:find('&', 1, true) then", 'if false then'),
    ('player stats: the apostrophe entity kept', PLAYER_STATS, """:gsub('&#39;', "'")""", ''),
    ('player stats: a double quote not escaped', PLAYER_STATS,
     """:gsub('"', '\\\\"') .. '"'""", """ .. '"'"""),
    ('player stats: keeper numbers from the outfield query', PLAYER_STATS,
     "\t\tif keeper then\n\t\t\tprimeKeeper(frame, player)", "\t\tif false then\n\t\t\tprimeKeeper(frame, player)"),
    # Module:FootballDate - every piece of the text and every way out to the template.
    ('date: months shifted by one', DATE,
     "'ינואר', 'פברואר', 'מרץ',", "'פברואר', 'ינואר', 'מרץ',"),
    ('date: the link keeps no zero', DATE,
     "'[[%s ב%s|%d ב%s]] [[%s]]', day,", "'[[%s ב%s|%d ב%s]] [[%s]]', tonumber(day),"),
    ('date: the text keeps the zero', DATE,
     "|%d ב%s]] [[%s]]', day, monthName, tonumber(day)",
     "|%s ב%s]] [[%s]]', day, monthName, day"),
    ('date: year unlinked', DATE, "[[%s]]', day", "%s', day"),
    ('date: a time accepted', DATE, "(%d%d)$')", "(%d%d)')"),
    ('date: untrimmed', DATE, "mw.text.trim(frame.args[1] or '')", "(frame.args[1] or '')"),
    ('date: day 0 accepted', DATE, 'tonumber(day) < 1', 'tonumber(day) < 0'),
    ('date: day 32 accepted', DATE, 'tonumber(day) > 31', 'tonumber(day) > 32'),
    ('date: fallback loses the date', DATE,
     "args = { ['תאריך'] = date }", "args = {}"),
    # Module:FootballSeasonTable - every line that decides a row or its place.
    ('season table: wins counts draws', SEASON_TABLE,
     "wins(1) .. '=wins, '", "wins(2) .. '=wins, '"),
    ('season table: losses counts wins', SEASON_TABLE,
     "wins(3) .. '=losses'", "wins(1) .. '=losses'"),
    ('season table: one row per season, competitions merged', SEASON_TABLE,
     "groupBy = 'Football_Games.Season, Football_Games.Competition',",
     "groupBy = 'Football_Games.Season',"),
    ('season table: seasons unordered', SEASON_TABLE,
     "orderBy = 'Football_Games.Season DESC',", ''),
    ('season table: cup before league', SEASON_TABLE,
     'local LEAGUE, CUP, OTHER = 1, 2, 3', 'local LEAGUE, CUP, OTHER = 2, 1, 3'),
    ('season table: the cup flag ignored', SEASON_TABLE,
     'elseif tonumber(row.trophy) == 1 then', 'elseif false then'),
    ('season table: rows sorted across seasons', SEASON_TABLE,
     'if index > 1 and row.season ~= rows[index - 1].season then', 'if false then'),
    ('season table: names in reverse', SEASON_TABLE,
     'return first.competition < second.competition',
     'return first.competition > second.competition'),
    ('season table: an empty list queries everything', SEASON_TABLE,
     'if given == 0 then', 'if false then'),
    ('season table: links without the exists check', SEASON_TABLE,
     'local title = mw.title.new(target)\n\tif title and title.exists then',
     'local title = mw.title.new(target)\n\tif title then'),
    ('season table: grouping links without the exists check', SEASON_TABLE,
     "local title = grouping ~= '' and mw.title.new(grouping) or nil\n\tif title and title.exists then",
     "local title = grouping ~= '' and mw.title.new(grouping) or nil\n\tif title then"),
    ('season table: decimals printed raw', SEASON_TABLE,
     'return tostring(tonumber(value) or 0)', 'return tostring(value)'),
    ('season table: rows run together', SEASON_TABLE,
     "return table.concat(html, '\\n')", "return table.concat(html, '')"),
    ('season table: one map lookup per row, not per competition', SEASON_TABLE,
     'if byName[entry.competition] == nil then', 'if true then'),
    ('season table: the lookup matches a whole list instead of HOLDS', SEASON_TABLE,
     """where = 'Names HOLDS "' .. competition .. '"'""", """where = 'Names = "' .. competition .. '"'"""),
    ('season table: the lookup takes any row', SEASON_TABLE,
     """'"', limit = 1 })""", """'"', limit = 2 })"""),
    ('season table: a quoted competition looked up anyway', SEASON_TABLE,
     """if competition:find('"', 1, true) or competition:find('&', 1, true) then""", 'if false then'),
    ('season table: a missing grouping page shows the competition', SEASON_TABLE,
     '\treturn grouping\nend', '\treturn competition\nend'),
    ('season table: the grouping link reads the grouping name', SEASON_TABLE,
     "return '[[' .. grouping .. '|' .. competition .. ']]'",
     "return '[[' .. grouping .. '|' .. grouping .. ']]'"),
    ('season table: two filters accepted', SEASON_TABLE, 'if given > 1 then', 'if false then'),
    ('season table: the map never read', SEASON_TABLE,
     "if trim(frame.args['קישור מפעל']) == 'מרכז' then", 'if false then'),
    ('season table: the assistant filter dropped', SEASON_TABLE,
     "local ENTITIES = { 'יריבות', 'שופט', 'עוזר שופט' }", "local ENTITIES = { 'יריבות', 'שופט' }"),
    ('season table: the class quote left open', SEASON_TABLE,
     """return '<div class="table-row">'""", """return '<div class="table-row>'"""),
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
     'if multiplyingJoined(builder.tables) and not builder.teamConstrained\n'
     '\t\t\t\tand not skipDefaults then',
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
    ('sort removed', LOGIC, '\t\ttable.sort(names)\n\n\t\tfor _, name in ipairs(names) do',
     '\n\t\tfor _, name in ipairs(names) do'),
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
     "\t\t\t\tgrain = 'event',\n\t\t\t\t-- מספר אירוע is a football filter",
     "\t\t\t\t-- מספר אירוע is a football filter"),
    ('the probe counts games instead of events', LOGIC,
     "\t\t\t\tgrain = 'event',\n\t\t\t\t-- מספר אירוע is a football filter",
     "\t\t\t\tgrain = 'game',\n\t\t\t\t-- מספר אירוע is a football filter"),
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
    ('תיקו and הפסד swapped', FIELDS,
     "['תיקו'] = 'Football_Games.ResultOpt = 2',", "['תיקו'] = 'Football_Games.ResultOpt = 3',"),
    ('the no-rows guard is removed', LOGIC,
     'if not rows[1] then', 'if false then'),
    ('ליגה repointed to Trophy', FIELDS,
     "\t\t\t['ליגה'] = 'Competitions.League = 1',",
     "\t\t\t['ליגה'] = 'Competitions.Trophy = 1',"),
    ('יתר-רשמיים loses its exclusions', FIELDS,
     """\t\t\t['יתר-רשמיים'] = '(Competitions.Official = 1 AND Competitions.League = 0'""",
     """\t\t\t['יתר-רשמיים'] = '(Competitions.Official = 1 AND Competitions.League >= 0'"""),
    ('גביע repointed to League', FIELDS,
     "\t\t\t['גביע'] = 'Competitions.Trophy = 1'",
     "\t\t\t['גביע'] = 'Competitions.League = 1'"),
    ('בינלאומי repointed', FIELDS,
     "\t\t\t['בינלאומי'] = 'Competitions.International = 1'",
     "\t\t\t['בינלאומי'] = 'Competitions.League = 1'"),
    ('רשמי repointed', FIELDS,
     "\t\t\t['רשמי'] = 'Competitions.Official = 1'",
     "\t\t\t['רשמי'] = 'Competitions.League = 1'"),
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
     "\t\t\t\t\tand cellBuilder.tables[multiplying] then",
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
     '\t\tlocal teamDefaultNeeded = multiplying ~= nil',
     '\t\tlocal teamDefaultNeeded = sharedBuilder.tables[multiplying]'),
    ('side constraint removed from the cells', LOGIC,
     'if teamDefaultNeeded and not cellBuilder.teamConstrained',
     'if false and not cellBuilder.teamConstrained'),
    ('modifiers read from the cell alone', LOGIC,
     'local cellBuilder = buildInto(cell.filters or {}, true, modifiers)',
     'local cellBuilder = buildInto(cell.filters or {}, true)'),
    # Renderer and block data.
    ('prime uses one constant category for every tab', RENDERER,
     "filters['קטגוריית מפעל'] = tab\n", "filters['קטגוריית מפעל'] = 'ליגה'\n"),
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
     '\t\t\tif cell.sum then\n\t\t\t\t-- A cell that sums a column',
     '\t\t\tif false then\n\t\t\t\t-- A cell that sums a column'),
    ('goals for and against are summed from the same column', FIELDS,
     "['ספיגות'] = 'Football_Games.ResultOpponent',",
     "['ספיגות'] = 'Football_Games.ResultMaccabi',"),
    ('a summing cell may join the events table', LOGIC,
     "if columnGrain == 'game' and multiplying then",
     'if false then'),
    ('a summing cell may be event grain', LOGIC,
     "if columnGrain == 'game' and grain ~= 'game' then", 'if false then'),
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
     "if tab.label:find('=', 1, true) or tab.label:find('|', 1, true) then",
     'if false then'),
    ('a tab strip without a heading gets no message', RENDERER,
     'if not heading then', 'if false then'),
    ('render accepts a block with no tab strip', RENDERER,
     'if not declaration.tabStrip then', 'if false then'),
    ('the skin loses the wrapper it scopes the tabs to', RENDERER,
     '\'<div class="tabber-converted">\'', "'<div>'"),
    ('the first tab shows the officials category', BLOCKS,
     "tabStrip = {\n\t\t\t{ category = 'ליגה', label = 'ליגה', heading = 'ליגה' },",
     "tabStrip = {\n\t\t\t{ category = 'רשמי', label = 'ליגה', heading = 'ליגה' },"),
    ('the cup tab is headed by its label', BLOCKS,
     "heading = 'גביע המדינה' },\n\t\t\t{ category = 'בינלאומי', label = 'אירופה', heading = 'אירופה' },\n\t\t\t{ category = 'רשמי', label = 'כל המסגרות',",
     "heading = 'גביע' },\n\t\t\t{ category = 'בינלאומי', label = 'אירופה', heading = 'אירופה' },\n\t\t\t{ category = 'רשמי', label = 'כל המסגרות',"),
    # The same two rules on the referee widget's own tab strip.
    ('the referee cup tab is headed by its label', BLOCKS,
     "heading = 'גביע המדינה' },\n\t\t\t{ category = 'בינלאומי', label = 'אירופה', heading = 'אירופה' },\n\t\t},",
     "heading = 'גביע' },\n\t\t\t{ category = 'בינלאומי', label = 'אירופה', heading = 'אירופה' },\n\t\t},"),
    # Leaderboards: 32 template queries on a referee page become one.
    ('ties keep the order the database returned', LOGIC,
     'return left.name < right.name', 'return false'),
    ('players with a zero count are ranked and counted', LOGIC,
     'if entry.count > 0 or keepZero then', 'if true then'),
    ('"עוד" at exactly ten, like Cargo', LOGIC,
     'more = #ranked > top,', 'more = #ranked >= top,'),
    ('the event-type union is never added to the WHERE', LOGIC,
     'if everyColumn then', 'if false then'),
    ('the union is added even when a column counts any event', LOGIC,
     '\t\t\t\teveryColumn = false\n\t\t\t\tbreak', '\t\t\t\tbreak'),
    ('opponent players are grouped again', LOGIC,
     '\t\tif not anySide then\n\t\t\tnarrowed[sideFilter] = Fields.sides.maccabiValue',
     '\t\tif false then\n\t\t\tnarrowed[sideFilter] = Fields.sides.maccabiValue'),
    ('a side column still gets Team = 1 in the WHERE', LOGIC,
     "\t\t\tif column.filters and column.filters[sideFilter] ~= nil then\n\t\t\t\tanySide = true",
     "\t\t\tif false then\n\t\t\t\tanySide = true"),
    ('the group key is not selected', LOGIC,
     "key .. '=g,' .. table.concat(compiled.fields, ',')",
     "table.concat(compiled.fields, ',')"),
    ('the leaderboard query is cut at ten rows', LOGIC,
     '\t\t\tlimit = Fields.maxLimit,', '\t\t\tlimit = 10,'),
    ('leaderboard accepts any option', LOGIC,
     "if name ~= 'groupBy' and name ~= 'top' and name ~= 'keepZero' then", 'if false then'),
    ('leaderboard top is not validated', LOGIC,
     'if not top or top < 1 or top ~= math.floor(top) then', 'if false then'),
    ('an empty referee name reaches the query', RENDERER,
     "if entity == '' then", 'if false then'),
    ('the widget reads extra direct arguments', RENDERER,
     "if key ~= 'בלוק' and key ~= declaration.entity then", 'if false then'),
    ('the "עוד" page starts at row one', RENDERER,
     'offset = tostring(declaration.top),', "offset = '0',"),
    ('the "עוד" page has no tiebreak', RENDERER,
     "order_by = 'COUNT(*) DESC, ' .. key,", "order_by = 'COUNT(*) DESC',"),
    ('the "עוד" link forgets its own column', LOGIC,
     "where = compiled.where .. ' AND ' .. compiled.aliases[1].condition,",
     'where = compiled.where,'),
    ('the "עוד" link is rebuilt from filter names again', RENDERER,
     'local query = FootballQueries.leaderboardColumnQuery(shared, columns, columnName)',
     "local query = FootballQueries.build({ ['עוזר שופט'] = 'x', ['קטגוריית מפעל'] = 'ליגה' })"),
    ('rows pass name and count swapped', RENDERER,
     'args = { row.name, tostring(row.count) },',
     'args = { tostring(row.count), row.name },'),
    ('the heading shows the box title instead of the noun', RENDERER,
     'result.players, box.noun) }', 'result.players, box.title) }'),
    ('the referee tabs lose Official = 1', BLOCKS,
     "entityFilter = 'עוזר שופט',\n\t\t-- Every tab of the templates' query carries"
     " Competitions.Official = 1,\n\t\t-- the league tab included - so רשמי is"
     " SHARED, and each tab's own\n\t\t-- category joins it inside its column.\n"
     "\t\tshared = { ['קטגוריית מפעל'] = 'רשמי' },",
     "entityFilter = 'עוזר שופט',\n\t\tshared = {},"),
    ('the season tabs lose Official = 1', BLOCKS,
     "entityFilter = 'עונה',\n\t\tshared = { ['קטגוריית מפעל'] = 'רשמי' },",
     "entityFilter = 'עונה',\n\t\tshared = {},"),
    ('the cards box counts every card, not yellows', BLOCKS,
     "{ key = 'cards', title = 'שיאני צהובים', noun = 'שחקנים שונים',\n"
     "\t\t\t  filters = { ['מספר אירוע'] = '7', ['תת אירוע'] = '71' } },",
     "{ key = 'cards', title = 'שיאני צהובים', noun = 'שחקנים שונים',\n"
     "\t\t\t  filters = { ['מספר אירוע'] = '7' } },"),
    ('the season cards box counts every card, not yellows', BLOCKS,
     "{ key = 'cards', title = 'שיאני מוצהבים', noun = 'שחקנים שונים',\n"
     "\t\t\t  filters = { ['מספר אירוע'] = '7', ['תת אירוע'] = '71' } },",
     "{ key = 'cards', title = 'שיאני מוצהבים', noun = 'שחקנים שונים',\n"
     "\t\t\t  filters = { ['מספר אירוע'] = '7' } },"),
    ('the goals box counts own goals', BLOCKS,
     "{ key = 'goals', title = 'שיאני כיבושים', noun = 'כובשים שונים',\n"
     "\t\t\t  -- Own goals out, for this box only. In the shared WHERE it\n"
     "\t\t\t  -- would also drop subtype-33 rows from the other boxes.\n"
     "\t\t\t  filters = { ['מספר אירוע'] = '3', ['ללא תת אירוע'] = '33' } },",
     "{ key = 'goals', title = 'שיאני כיבושים', noun = 'כובשים שונים',\n"
     "\t\t\t  filters = { ['מספר אירוע'] = '3' } },"),
    ('the season goals box counts own goals', BLOCKS,
     "{ key = 'goals', title = 'שיאני כיבושים', noun = 'כובשים שונים',\n"
     "\t\t\t  filters = { ['מספר אירוע'] = '3', ['ללא תת אירוע'] = '33' } },",
     "{ key = 'goals', title = 'שיאני כיבושים', noun = 'כובשים שונים',\n"
     "\t\t\t  filters = { ['מספר אירוע'] = '3' } },"),
    # boxOpen: no default, and each block's own wrapper must not drift onto
    # the other's - the season box must never gain id="שיאנים", and the
    # referee box must never lose it.
    ('referee boxOpen loses its id', BLOCKS,
     "boxOpen = '<div class=\"records-list-tabs-container\" id=\"שיאנים\">',",
     "boxOpen = '<div class=\"records-list-tabs-container\">',"),
    # Survived the old substring check: the id is still there, so contains()
    # passed. The referee wrapper is live markup, so the test is exact now.
    ('referee boxOpen gains an attribute', BLOCKS,
     "boxOpen = '<div class=\"records-list-tabs-container\" id=\"שיאנים\">',",
     "boxOpen = '<div class=\"records-list-tabs-container\" id=\"שיאנים\" dir=\"rtl\">',"),
    ('season boxOpen gains the referee id', BLOCKS,
     "\t\tboxOpen = '<div class=\"records-list-tabs-container\">',\n\n"
     "\t\ttabStrip = {\n\t\t\t{ category = 'רשמי', label = 'משחקים רשמיים',\n"
     "\t\t\t  heading = 'משחקים רשמיים' },\n"
     "\t\t\t{ category = 'ליגה', label = 'ליגה', heading = 'ליגה' },\n"
     "\t\t\t{ category = 'גביע', label = 'גביע', heading = 'גביע המדינה' },\n"
     "\t\t\t{ category = 'בינלאומי', label = 'בינלאומי', heading = 'בינלאומי' },",
     "\t\tboxOpen = '<div class=\"records-list-tabs-container\" id=\"שיאנים\">',\n\n"
     "\t\ttabStrip = {\n\t\t\t{ category = 'רשמי', label = 'משחקים רשמיים',\n"
     "\t\t\t  heading = 'משחקים רשמיים' },\n"
     "\t\t\t{ category = 'ליגה', label = 'ליגה', heading = 'ליגה' },\n"
     "\t\t\t{ category = 'גביע', label = 'גביע', heading = 'גביע המדינה' },\n"
     "\t\t\t{ category = 'בינלאומי', label = 'בינלאומי', heading = 'בינלאומי' },"),
    ('season tab 4 reads אירופה like the referee block', BLOCKS,
     "{ category = 'בינלאומי', label = 'בינלאומי', heading = 'בינלאומי' },\n\t\t},\n"
     "\t\ttabHeading = '<div class=\"tab-header\">%s (%s %s)</div>',\n\n"
     "\t\tboxes = {\n\t\t\t{ key = 'appearances', title = 'שיאני הופעות',",
     "{ category = 'בינלאומי', label = 'אירופה', heading = 'אירופה' },\n\t\t},\n"
     "\t\ttabHeading = '<div class=\"tab-header\">%s (%s %s)</div>',\n\n"
     "\t\tboxes = {\n\t\t\t{ key = 'appearances', title = 'שיאני הופעות',"),
    # The rest of the season block's data lines. Each is anchored on context
    # only the season block has (the id-less boxOpen, the בינלאומי tab, the
    # מוצהבים title) so it matches once, not in the referee block too.
    ('season shows nine rows, not ten', BLOCKS,
     "\t\ttop = 10,\n\t\trowTemplate = 'סטטיסטיקות/הצגת שיאנים/הצגת שחקן/כדורגל',\n"
     "\t\tmoreText = 'עוד',\n\t\tboxOpen = '<div class=\"records-list-tabs-container\">',",
     "\t\ttop = 9,\n\t\trowTemplate = 'סטטיסטיקות/הצגת שיאנים/הצגת שחקן/כדורגל',\n"
     "\t\tmoreText = 'עוד',\n\t\tboxOpen = '<div class=\"records-list-tabs-container\">',"),
    ('season "more" link reads differently', BLOCKS,
     "\t\tmoreText = 'עוד',\n\t\tboxOpen = '<div class=\"records-list-tabs-container\">',",
     "\t\tmoreText = 'עוד תוצאות',\n\t\tboxOpen = '<div class=\"records-list-tabs-container\">',"),
    ('season league heading changes', BLOCKS,
     "\t\t\t{ category = 'ליגה', label = 'ליגה', heading = 'ליגה' },\n"
     "\t\t\t{ category = 'גביע', label = 'גביע', heading = 'גביע המדינה' },\n"
     + SEASON_TAB_TAIL,
     "\t\t\t{ category = 'ליגה', label = 'ליגה', heading = 'ליגת העל' },\n"
     "\t\t\t{ category = 'גביע', label = 'גביע', heading = 'גביע המדינה' },\n"
     + SEASON_TAB_TAIL),
    ('season cup heading equals its label', BLOCKS,
     "\t\t\t{ category = 'גביע', label = 'גביע', heading = 'גביע המדינה' },\n"
     + SEASON_TAB_TAIL,
     "\t\t\t{ category = 'גביע', label = 'גביע', heading = 'גביע' },\n"
     + SEASON_TAB_TAIL),
    ('season appearances noun changes', BLOCKS,
     "\t\t\t{ key = 'appearances', title = 'שיאני הופעות',\n"
     "\t\t\t  noun = 'מופיעים שונים',\n"
     "\t\t\t  filters = { ['מספר אירוע'] = '1,5' } },\n"
     "\t\t\t{ key = 'goals', title = 'שיאני כיבושים', noun = 'כובשים שונים',\n"
     "\t\t\t  filters = { ['מספר אירוע'] = '3', ['ללא תת אירוע'] = '33' } },",
     "\t\t\t{ key = 'appearances', title = 'שיאני הופעות',\n"
     "\t\t\t  noun = 'שחקנים שונים',\n"
     "\t\t\t  filters = { ['מספר אירוע'] = '1,5' } },\n"
     "\t\t\t{ key = 'goals', title = 'שיאני כיבושים', noun = 'כובשים שונים',\n"
     "\t\t\t  filters = { ['מספר אירוע'] = '3', ['ללא תת אירוע'] = '33' } },"),
    # The season-numbers blocks: every cell's filter, the tab list, and the
    # renderer's handling of a block that declares no rows.
    ('season numbers: wins count draws', BLOCKS,
     "{ name = 'wins', grain = 'game', filters = { ['תוצאה'] = 'ניצחון' } },\n"
     "\t\t\t{ name = 'draws', grain = 'game', filters = { ['תוצאה'] = 'תיקו' } },\n"
     "\t\t\t{ name = 'losses', grain = 'game', filters = { ['תוצאה'] = 'הפסד' } },\n"
     "\t\t\t{ name = 'goalsFor'",
     "{ name = 'wins', grain = 'game', filters = { ['תוצאה'] = 'תיקו' } },\n"
     "\t\t\t{ name = 'draws', grain = 'game', filters = { ['תוצאה'] = 'תיקו' } },\n"
     "\t\t\t{ name = 'losses', grain = 'game', filters = { ['תוצאה'] = 'הפסד' } },\n"
     "\t\t\t{ name = 'goalsFor'"),
    ('season numbers: draws count losses', BLOCKS,
     "{ name = 'draws', grain = 'game', filters = { ['תוצאה'] = 'תיקו' } },\n"
     "\t\t\t{ name = 'losses', grain = 'game', filters = { ['תוצאה'] = 'הפסד' } },\n"
     "\t\t\t{ name = 'goalsFor'",
     "{ name = 'draws', grain = 'game', filters = { ['תוצאה'] = 'הפסד' } },\n"
     "\t\t\t{ name = 'losses', grain = 'game', filters = { ['תוצאה'] = 'הפסד' } },\n"
     "\t\t\t{ name = 'goalsFor'"),
    ('season numbers: losses count wins', BLOCKS,
     "{ name = 'losses', grain = 'game', filters = { ['תוצאה'] = 'הפסד' } },\n"
     "\t\t\t{ name = 'goalsFor'",
     "{ name = 'losses', grain = 'game', filters = { ['תוצאה'] = 'ניצחון' } },\n"
     "\t\t\t{ name = 'goalsFor'"),
    ('season numbers: goals for sum the goals against', BLOCKS,
     "{ name = 'goalsFor', grain = 'game', sum = 'כיבושים', filters = {} },\n"
     "\t\t\t{ name = 'goalsAgainst', grain = 'game', sum = 'ספיגות', filters = {} },\n"
     "\t\t\t{ name = 'cleanSheets'",
     "{ name = 'goalsFor', grain = 'game', sum = 'ספיגות', filters = {} },\n"
     "\t\t\t{ name = 'goalsAgainst', grain = 'game', sum = 'ספיגות', filters = {} },\n"
     "\t\t\t{ name = 'cleanSheets'"),
    ('season numbers: goals against sum the goals for', BLOCKS,
     "{ name = 'goalsAgainst', grain = 'game', sum = 'ספיגות', filters = {} },\n"
     "\t\t\t{ name = 'cleanSheets'",
     "{ name = 'goalsAgainst', grain = 'game', sum = 'כיבושים', filters = {} },\n"
     "\t\t\t{ name = 'cleanSheets'"),
    ('season numbers: a clean sheet lets in one', BLOCKS,
     "{ name = 'cleanSheets', grain = 'game', filters = { ['תוצאה יריבה'] = '0' } },",
     "{ name = 'cleanSheets', grain = 'game', filters = { ['תוצאה יריבה'] = '1' } },"),
    ('season numbers: yellows count reds', BLOCKS,
     "{ name = 'yellows', grain = 'event',\n\t\t\t  filters = { ['תת אירוע'] = '71', ['מכבי'] = 'כן' } },",
     "{ name = 'yellows', grain = 'event',\n\t\t\t  filters = { ['תת אירוע'] = '72', ['מכבי'] = 'כן' } },"),
    ('season numbers: yellows are the opponent\'s', BLOCKS,
     "{ name = 'yellows', grain = 'event',\n\t\t\t  filters = { ['תת אירוע'] = '71', ['מכבי'] = 'כן' } },",
     "{ name = 'yellows', grain = 'event',\n\t\t\t  filters = { ['תת אירוע'] = '71', ['מכבי'] = 'לא' } },"),
    ('season numbers: reds lose the second-yellow red', BLOCKS,
     "filters = { ['תת אירוע'] = '72, 73', ['מכבי'] = 'כן' } },",
     "filters = { ['תת אירוע'] = '72', ['מכבי'] = 'כן' } },"),
    ('season numbers: reds are the opponent\'s', BLOCKS,
     "filters = { ['תת אירוע'] = '72, 73', ['מכבי'] = 'כן' } },",
     "filters = { ['תת אירוע'] = '72, 73', ['מכבי'] = 'לא' } },"),
    ('season numbers: the results block loses its international tab', BLOCKS,
     "['season-results'] = {\n\t\tentity = 'עונה',\n"
     "\t\ttabs = { 'רשמי', 'ליגה', 'גביע', 'בינלאומי' },",
     "['season-results'] = {\n\t\tentity = 'עונה',\n"
     "\t\ttabs = { 'רשמי', 'ליגה', 'גביע' },"),
    ('prime stores nothing for a block without rows', RENDERER,
     "block.rows and renderRows(block, tabCells) or PRIMED })",
     "block.rows and renderRows(block, tabCells) or '' })"),
    ('tab shows a rowless block\'s marker', RENDERER,
     "\tif not declaration.rows then\n",
     "\tif false then\n"),
    # The stadium block is derived from the season block; its three lines.
    ('stadium derives from the referee block', BLOCKS,
     "blocks['stadium'] = copied(blocks['season'])",
     "blocks['stadium'] = copied(blocks['referee-assistant'])"),
    ('stadium takes a single stadium argument', BLOCKS,
     "blocks['stadium'].entity = 'אצטדיונים'",
     "blocks['stadium'].entity = 'אצטדיון'"),
    ('stadium filters through the alias lookup', BLOCKS,
     "blocks['stadium'].entityFilter = 'אצטדיונים'",
     "blocks['stadium'].entityFilter = 'אצטדיון'"),
    ('stadium filters by season', BLOCKS,
     "blocks['stadium'].entityFilter = 'אצטדיונים'",
     "blocks['stadium'].entityFilter = 'עונה'"),
    # The player-category pages: a quoted list, no "עוד" link.
    ('a quoted list keeps its quotes', RENDERER,
     "names[#names + 1] = (mw.text.trim(item):gsub('^\"(.*)\"$', '%1'))",
     'names[#names + 1] = mw.text.trim(item)'),
    ('an empty moreText still links', RENDERER,
     "if result.more and declaration.moreText ~= '' then", 'if result.more then'),
    ('the category list is not unquoted', BLOCKS,
     "blocks['player-category'].entityQuoted = true\n", ''),
    ('the category block links "עוד"', BLOCKS,
     "blocks['player-category'].moreText = ''\n", ''),
    ('the category block filters one player', BLOCKS,
     "blocks['player-category'].entityFilter = 'שחקנים'", "blocks['player-category'].entityFilter = 'שחקן'"),
    ('the category wrapper loses the page class', BLOCKS,
     "blocks['player-category'].boxOpen = '<div class=\"records-section-container records-list-tabs-container\">'",
     "blocks['player-category'].boxOpen = '<div class=\"records-list-tabs-container\">'"),
    # The players portal: all-time blocks with no entity.
    ('a block with no entity demands one anyway', RENDERER,
     '\tif declaration.entity then\n', '\tif true then\n'),
    ('the portal keeps every season box', BLOCKS, '\tblock.boxes = {}\n', ''),
    ('the portal boxes swap order', BLOCKS,
     "{ 'goals', 'assists' }, { 'שיאני כיבושים', 'שיאני בישולים ' })",
     "{ 'assists', 'goals' }, { 'שיאני כיבושים', 'שיאני בישולים ' })"),
    ('the assists title loses its trailing space', BLOCKS,
     "{ 'שיאני כיבושים', 'שיאני בישולים ' })", "{ 'שיאני כיבושים', 'שיאני בישולים' })"),
    ('the portal wrapper loses the row styling class', BLOCKS,
     "block.boxOpen = '<div class=\"records-container records-list-tabs-container\">'",
     "block.boxOpen = '<div class=\"records-container\">'"),
    ('the portal titles are the season\'s', BLOCKS,
     '\t\tbyKey[key].title = titles[index]\n', ''),
    # The main-referee block, derived from the season block.
    ('referee-main derives from the assistant block', BLOCKS,
     "blocks['referee-main'] = copied(blocks['season'])",
     "blocks['referee-main'] = copied(blocks['referee-assistant'])"),
    ('referee-main takes the assistant argument', BLOCKS,
     "blocks['referee-main'].entity = 'שופט'",
     "blocks['referee-main'].entity = 'עוזר שופט'"),
    ('referee-main filters the assistants', BLOCKS,
     "blocks['referee-main'].entityFilter = 'שופט'",
     "blocks['referee-main'].entityFilter = 'עוזר שופט'"),
    ('referee-main puts the id on the second box', BLOCKS,
     "blocks['referee-main'].boxes[1].boxOpen =",
     "blocks['referee-main'].boxes[2].boxOpen ="),
    ('referee-main cards box keeps the season title', BLOCKS,
     "blocks['referee-main'].boxes[4].title = 'שיאני צהובים'",
     "blocks['referee-main'].boxes[4].title = 'שיאני מוצהבים'"),
    ('a box\'s own wrapper is ignored', RENDERER,
     'box.boxOpen or declaration.boxOpen,', 'declaration.boxOpen,'),
    ('season assists title changes', BLOCKS,
     "{ key = 'assists', title = 'שיאני בישולים', noun = 'שחקנים שונים',\n"
     "\t\t\t  filters = { ['מספר אירוע'] = '4' } },\n"
     "\t\t\t{ key = 'cards', title = 'שיאני מוצהבים',",
     "{ key = 'assists', title = 'שיאני מבשלים', noun = 'שחקנים שונים',\n"
     "\t\t\t  filters = { ['מספר אירוע'] = '4' } },\n"
     "\t\t\t{ key = 'cards', title = 'שיאני מוצהבים',"),
    # Module:FootballSeasonSquad - byte-identity with the squad templates.
    ('squad: list split keeps untrimmed names', SQUAD,
     'items[#items + 1] = trim(part)', 'items[#items + 1] = part'),
    ('squad: unique keeps empty names', SQUAD,
     "if item ~= '' and not seen[item] then", 'if not seen[item] then'),
    ('squad: unique keeps repeats', SQUAD,
     "if item ~= '' and not seen[item] then", "if item ~= '' then"),
    ('squad: season check accepts anything', SQUAD,
     "if not season:match('^[%d/]*$') then", 'if false then'),
    ('squad: shirt numbers counted by event rows, not games', SQUAD,
     "'COUNT(DISTINCT fg._pageName)=games, MIN(fg.Date)=firstGame'",
     "'COUNT(*)=games, MIN(fg.Date)=firstGame'"),
    ('squad: no-season guard dropped from the players query', SQUAD,
     '\tif not season then\n\t\treturn {}, {}\n\tend\n', ''),
    ('squad: no-season guard dropped from the numbers query', SQUAD,
     '\tif not season then\n\t\treturn {}\n\tend\n', ''),
    ('squad: double quote not escaped', SQUAD,
     """:gsub('"', '\\\\"')""", ''),
    ('squad: season query loses Team', SQUAD,
     """'1=1 AND fg.Season="' .. season .. '" AND ge.Team=1',""",
     """'1=1 AND fg.Season="' .. season .. '"',"""),
    ('squad: season query groups nothing', SQUAD,
     "\t\tgroupBy = 'ge.PlayerName',\n", ''),
    ('squad: season games not counted', SQUAD,
     'games[names[index]] = tonumber(row.games) or 0', 'games[names[index]] = 0'),
    ('squad: position code ignored', SQUAD,
     'inPosition = held[position.code]', "inPosition = held['1']"),
    ('squad: ללא עמדה forgets attackers', SQUAD,
     "inPosition = not (held['1'] or held['2'] or held['3'] or held['4'])",
     "inPosition = not (held['1'] or held['2'] or held['3'])"),
    ('squad: apostrophe fix dropped', SQUAD,
     """:gsub('&#39;', "'")""", ''),
    ('squad: last profile row wins', SQUAD,
     "if page ~= '' and not byPage[page] then", "if page ~= '' then"),
    ('squad: empty page name kept', SQUAD,
     "if page ~= '' and not byPage[page] then", 'if not byPage[page] then'),
    ('squad: cards left in query order', SQUAD,
     'table.sort(list, cardOrder(byPage, games))', ''),
    ('squad: missing MainNumber sorts last', SQUAD,
     'if firstNumber == nil then return true end', 'if firstNumber == nil then return false end'),
    ('squad: MainNumber descending', SQUAD,
     'return firstNumber < secondNumber', 'return firstNumber > secondNumber'),
    ('squad: MainNumber compared as text', SQUAD,
     'local firstNumber = tonumber(byPage[first].mainNumber)',
     'local firstNumber = byPage[first].mainNumber'),
    ('squad: fewer games first', SQUAD,
     'return firstGames > secondGames', 'return firstGames < secondGames'),
    ('squad: games ignored in the order', SQUAD,
     'if firstGames ~= secondGames then', 'if false then'),
    ('squad: name tie-break reversed', SQUAD,
     'return first < second', 'return first > second'),
    ('squad: limit guard >= to >', SQUAD,
     'if #rows >= QUERY_LIMIT then', 'if #rows > QUERY_LIMIT then'),
    ('squad: numbers count blank shirts', SQUAD,
     """\t\t\t\t.. '" AND ge.PlayerNumber != ""',""", """\t\t\t\t.. '"',"""),
    ('squad: numbers grouped by player only', SQUAD,
     "groupBy = 'ge.PlayerName, ge.PlayerNumber',", "groupBy = 'ge.PlayerName',"),
    ('squad: fewer games win', SQUAD,
     'if not current or games > current.games', 'if not current or games < current.games'),
    ('squad: ties go to the latest game', SQUAD,
     'firstGame < current.firstGame', 'firstGame > current.firstGame'),
    ('squad: games compared as strings', SQUAD,
     'local name, games = trim(row.name), tonumber(row.games) or 0',
     'local name, games = trim(row.name), row.games or 0'),
    ('squad: zero number shown', SQUAD,
     "if number and number ~= '' and not numericallyEqual(number, 0) then",
     "if number and number ~= '' then"),
    ('squad: flags compared as text', SQUAD,
     '\t\treturn number == target\n', '\t\treturn value == target\n'),
    ('squad: captain double quote kept raw', SQUAD,
     """fullName = trim(fullName):gsub('"', '&quot;')""", 'fullName = trim(fullName)'),
    ('squad: empty full name can be a captain', SQUAD,
     "\tif fullName == '' then\n\t\treturn false\n\tend\n", ''),
    ('squad: captain matches the page name', SQUAD,
     'isCaptain(captains, profile.fullName)', 'isCaptain(captains, page)'),
    ('squad: link ignores missing pages', SQUAD,
     'if title and title.exists then', 'if title then'),
    ('squad: nowiki dropped from the link', SQUAD,
     "frame:extensionTag('nowiki', ' ')", "' '"),
    ('squad: home and rooted icons swapped', SQUAD,
     "if numericallyEqual(profile.homePlayer, 1) then icons[#icons + 1] = ICONS.homePlayer end",
     "if numericallyEqual(profile.homePlayer, 1) then icons[#icons + 1] = ICONS.rootedPlayer end"),
    ('squad: card keeps its trailing newline', SQUAD,
     """'\\n</span>\\n</div>'\nend""", """'\\n</span>\\n</div>\\n'\nend"""),
    ('squad: empty-first-name check dropped', SQUAD,
     "local listed = (players[1] or '') ~= ''", 'local listed = #players > 0'),
    ('squad: empty-first-name check skips only the list shell', SQUAD,
     'if listed and #everyone > 0 then', 'if #everyone > 0 then'),
    ('squad: player names not deduplicated', SQUAD,
     'local everyone = unique(players)', 'local everyone = players'),
    ('squad: empty position still rendered', SQUAD,
     'if #lists[index] > 0 then', 'if true then'),
    ('squad: numbers read the argument, not the page variable', SQUAD,
     "frame:callParserFunction('#var', { 'עונה להצגה' })", 'season'),
    ('squad: hand-entered list ignored', SQUAD,
     "trim(given) ~= '' and splitList(given) or seasonNames", 'seasonNames'),
]


def suites_pass() -> bool:
    for suite in SUITES:
        result = subprocess.run(['lua5.1', suite], capture_output=True)
        if result.returncode != 0:
            return False
    return True


def deeper(pattern: str) -> str:
    """The pattern one tab deeper: every indented line gets one more tab, blank
    lines stay blank (the factory bodies were indented that way), and a line
    that starts mid-way (no leading tab) is left alone."""
    lines = pattern.split('\n')
    return '\n'.join(('\t' + line) if line.startswith('\t') else line for line in lines)


def main() -> None:
    if not suites_pass():
        sys.exit('the suites fail before any mutation - fix that first')

    killed, survived, broken = 0, [], []

    for label, path, find, replace in MUTATIONS:
        original = path.read_text(encoding='utf-8')
        occurrences = original.count(find)
        # The shared modules (SportQueries, StatsBlock) hold the football bodies
        # indented one tab inside a factory. A multi-line pattern written at
        # the original indentation is retried one tab deeper - the same text,
        # so the "exactly once" rule below still guards it.
        if occurrences == 0 and '\n' in find and path in (LOGIC, RENDERER):
            find, replace = deeper(find), deeper(replace)
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
