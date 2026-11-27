--[[
Module:FootballCompetition - the game tables of a football competition page.

Wiki page: Module:FootballCompetition

The subpages of תבנית:מפעל כדורגל built their #cargo_query from the names with
{{המרות/שם ללא גרש וגרשיים}}, which strips the apostrophe that
Football_Games.Competition keeps - so גביע מלצ'ט showed none of its games. The
WHERE here comes from Module:FootballQueries, whose quote rule for that column
is the measured one. The rest of each query is the template's own, and each row
still goes through the template's row template.

    {{#invoke:FootballCompetition|biggest|תוצאה=ניצחון|מפעלים={{{מפעלים לשליפה|}}}}}
    {{#invoke:FootballCompetition|seasons|מפעלים={{{מפעלים|}}}}}
]]

local Queries = require('Module:FootballQueries')

local p = {}

--- The two tables of biggest results, by the result they rank.
local BIGGEST = {
	['ניצחון'] = {
		orderBy = '(Football_Games.ResultMaccabi-Football_Games.ResultOpponent) DESC',
		rowTemplate = 'מפעל כדורגל/הצגת הניצחונות הגדולים/הצגת משחק',
	},
	['הפסד'] = {
		orderBy = '(Football_Games.ResultOpponent-Football_Games.ResultMaccabi) DESC',
		rowTemplate = 'מפעל כדורגל/הצגת ההפסדים הגדולים/הצגת משחק',
	},
}

-- The templates showed ten rows and nothing more: a cut-off here is the
-- answer, not a truncation, so it is not guarded the way the layer's own
-- queries are.
local BIGGEST_ROWS = 10

-- The seasons table has no cut-off, so hitting this is an error.
local SEASONS_LIMIT = 500

--- Refuses any argument the entry point does not name, so a typo fails loudly
--- instead of being dropped.
local function argumentsOf(frame, allowed)
	local args = {}
	for name, value in pairs(frame.args) do
		if not allowed[name] then
			error(string.format('FootballCompetition: unknown argument "%s"', tostring(name)), 0)
		end
		args[name] = mw.text.trim(value)
	end
	return args
end

--- The query for the competitions' games, with `extra` filters, as the layer builds it.
local function gamesQuery(competitions, extra)
	local filters = { ['מפעלים'] = competitions }
	for name, value in pairs(extra or {}) do
		filters[name] = value
	end
	return Queries.build(filters)
end

local function rowsOf(frame, rows, template)
	local out = {}
	for _, row in ipairs(rows) do
		out[#out + 1] = frame:expandTemplate({ title = template, args = row })
	end
	return table.concat(out)
end

--- The ten biggest wins or losses, each through the row template.
function p.biggest(frame)
	local args = argumentsOf(frame, { ['תוצאה'] = true, ['מפעלים'] = true })
	local kind = BIGGEST[args['תוצאה'] or '']
	if not kind then
		error(string.format('FootballCompetition: biggest needs תוצאה=ניצחון or הפסד, got "%s"',
			tostring(args['תוצאה'])), 0)
	end
	-- No names, no games - an empty value would otherwise mean "every game".
	if (args['מפעלים'] or '') == '' then
		return ''
	end

	local query = gamesQuery(args['מפעלים'], { ['תוצאה'] = args['תוצאה'] })
	local rows = mw.ext.cargo.query(query.tables,
		'Football_Games._pageName=PageName, Football_Games.Season=Season, '
		.. 'Football_Games.Opponent=Opponent, Football_Games.Leg=Leg, '
		.. 'Football_Games.ResultMaccabi=ResultMaccabi, '
		.. 'Football_Games.ResultOpponent=ResultOpponent',
		{ join = query.join, where = query.where, orderBy = kind.orderBy, limit = BIGGEST_ROWS })
	return rowsOf(frame, rows, kind.rowTemplate)
end

--- Wins, draws and losses per season and competition, with the achievement of
--- that season - the rows of the seasonal-numbers table.
function p.seasons(frame)
	local args = argumentsOf(frame, { ['מפעלים'] = true })
	if (args['מפעלים'] or '') == '' then
		return ''
	end

	local query = gamesQuery(args['מפעלים'])
	local joins = { 'Football_Games.Season=Achievements.Season',
		'Football_Games.Competition=Achievements.Competition' }
	if query.join ~= '' then
		table.insert(joins, 1, query.join)
	end
	local rows = mw.ext.cargo.query(query.tables .. ',Achievements',
		'Football_Games.Season=Season, Achievements.Achievement=Achievement, '
		.. 'Achievements.Competition=Competition, '
		.. 'COUNT(CASE WHEN Football_Games.ResultOpt=1 THEN 1 ELSE NULL END)=WinningCount, '
		.. 'COUNT(CASE WHEN Football_Games.ResultOpt=2 THEN 2 ELSE NULL END)=TieCount, '
		.. 'COUNT(CASE WHEN Football_Games.ResultOpt=3 THEN 3 ELSE NULL END)=LoosingCount',
		{ join = table.concat(joins, ', '), where = query.where,
		  groupBy = 'Football_Games.Season, Football_Games.Competition, Achievements.Achievement',
		  orderBy = 'Football_Games.Season DESC', limit = SEASONS_LIMIT })
	if #rows >= SEASONS_LIMIT then
		error(string.format('FootballCompetition: %d season rows reached the limit', #rows), 0)
	end
	return rowsOf(frame, rows, 'מפעל כדורגל/הצגת מספרים עונתיים/הצגת נתונים')
end

return p
