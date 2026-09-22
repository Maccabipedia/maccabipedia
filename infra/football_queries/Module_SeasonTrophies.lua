--[=[
Module:SeasonTrophies - the competitions Maccabi won in a season, for three sports.

Wiki page: Module:SeasonTrophies

`כדורגל:עונות`, `כדורסל:עונות`, `כדורעף:עונות` and `עמוד ראשי` listed every season and asked
`<ענף>/שליפות/רשימת זכיות לעונה |עונה=X` for that season's wins - ONE #cargo_query per season:
102 + 75 + 55 = 232 queries on `עונות` alone, 0.8 of its 1.4 s. The first call for a sport here
runs ONE query for all of its winning seasons and stores each season's list in a page variable
(Scribunto keeps nothing between invokes); every later call reads the variable. Three queries a
page instead of 232.

    {{#invoke:SeasonTrophies|list|ענף=כדורגל|עונה={{{עונה|}}}}}

The first module serving more than one sport. Its sport keys are the contract for any later
multi-sport module: כדורגל, כדורסל, כדורעף, as the wiki spells them.

Mirroring the templates exactly (measured on production 2026-09-22):
  - the list is joined with a comma and TWO spaces, which is what Cargo's `no html` prints
    (`comma-separator` + ' '). The pages' #arraydefine trims either way, so this is invisible
    on the page and visible in the gate;
  - with no `order by` Cargo orders by the first field, so the old list was alphabetical by
    competition; this orders by it explicitly, since storage order can change on a recreateData;
  - a season with no wins gives '' (the templates' `default=`);
  - volleyball excludes הליגה הארצית, as its template did.
The football template keeps its own hardcoded 1966/68 answer, ahead of this call.
]=]

local p = {}

--- Per sport: the two Cargo tables, and competitions its template excluded.
-- Aliases are fixed (a, c) for every sport: they never reach the output, and the old
-- per-sport aliases (ba/bc, va/vc) would be three more strings with no behaviour behind them.
local SPORTS = {
	['כדורגל'] = { achievements = 'Achievements', competitions = 'Competitions' },
	['כדורסל'] = { achievements = 'Basketball_Achievements', competitions = 'Basketball_Competitions' },
	['כדורעף'] = { achievements = 'Volleyball_Achievements', competitions = 'Volleyball_Competitions',
		excluded = { 'הליגה הארצית' } },
}

-- Cargo's own default is 100 rows and it truncates in silence; basketball already has ~125
-- winning rows. A result that reached the limit is an error, never a short answer.
local ROW_LIMIT = 500

local SEPARATOR = ',  '

local function trim(value)
	return mw.text.trim(value or '')
end

local function variable(sport, season)
	return 'SeasonTrophies|' .. sport .. '|' .. season
end

local function store(frame, name, value)
	frame:callParserFunction('#vardefine', { name, value })
end

local function stored(frame, name)
	return frame:callParserFunction('#var', { name })
end

--- Every (season, competition) Maccabi won in this sport, in the templates' order.
local function prime(frame, sport)
	local declaration = SPORTS[sport]
	local where = 'c.Official AND a.Achievement="זכיה"'
	for _, competition in ipairs(declaration.excluded or {}) do
		where = where .. ' AND a.Competition != "' .. competition .. '"'
	end
	local rows = mw.ext.cargo.query(
		declaration.achievements .. '=a, ' .. declaration.competitions .. '=c',
		'a.Season=season, a.Competition=competition',
		{ join = 'a.Competition=c.OriginalName', where = where,
		  orderBy = 'a.Competition', limit = ROW_LIMIT })
	if #rows >= ROW_LIMIT then
		error('SeasonTrophies: ' .. sport .. ' reached the row limit of ' .. ROW_LIMIT
			.. ' - the lists would be cut', 0)
	end
	local lists = {}
	for _, row in ipairs(rows) do
		local season = row.season
		if lists[season] == nil then
			lists[season] = row.competition
		else
			lists[season] = lists[season] .. SEPARATOR .. row.competition
		end
	end
	for season, list in pairs(lists) do
		store(frame, variable(sport, season), list)
	end
end

function p.list(frame)
	local sport = trim(frame.args['ענף'])
	local season = trim(frame.args['עונה'])
	if SPORTS[sport] == nil then
		error('SeasonTrophies: unknown ענף "' .. sport .. '"', 0)
	end
	if season == '' then
		return ''
	end
	local marker = variable(sport, 'primed')
	if stored(frame, marker) == '' then
		prime(frame, sport)
		store(frame, marker, '1')
	end
	return stored(frame, variable(sport, season))
end

return p
