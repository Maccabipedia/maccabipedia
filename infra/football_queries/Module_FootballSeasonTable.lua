--[[
Module:FootballSeasonTable - the rows of a "season by season" table.

Wiki page: Module:FootballSeasonTable

תבנית:יריבת כדורגל/הצגת סטטיסטיקה עונתית listed the (season, competition)
pairs with one #cargo_query and rendered each through a row template that
ran `כמות נתוני משחק` three times - wins, draws, losses: 1 + 3N queries,
~300 on הפועל תל אביב. This renders the same rows from TWO queries: the
pairs with their three counts, and the competition catalogue for the order.

Template body (the section wrapper stays in the template, so its markup is
the template's own; only the #cargo_query is replaced):
    {{#invoke:FootballSeasonTable|rows|יריבות={{{יריבות לשליפה|}}}}}

Three deliberate changes, decided 2026-09-22:
  1. Every row. The template set no limit, so Cargo's silent default of 100
     cut the oldest seasons of the three clubs with more pairs.
  2. Within a season: league first, then cup, then the rest, then by name.
     Seasons stay in the database's `Season DESC` order; only the rows
     inside one season are regrouped (the template left that order to MySQL).
  3. A competition with no Competitions row (ידידות, גביע מלצ'ט) shows its
     real results. The template counted through the catalogue and showed
     0/0/0 for it.
]]

local FootballQueries = require('Module:FootballQueries')

local p = {}

local LEAGUE, CUP, OTHER = 1, 2, 3

local function trim(value)
	return mw.text.trim(value or '')
end

local function wins(result)
	return string.format(
		'SUM(CASE WHEN Football_Games.ResultOpt = %d THEN 1 ELSE 0 END)', result)
end

--- The (season, competition) pairs with their results, in `Season DESC`.
local function pairs_(filters)
	return FootballQueries.query(filters, {
		fields = 'Football_Games.Season=season, Football_Games.Competition=competition, '
			.. wins(1) .. '=wins, ' .. wins(2) .. '=draws, ' .. wins(3) .. '=losses',
		groupBy = 'Football_Games.Season, Football_Games.Competition',
		orderBy = 'Football_Games.Season DESC',
	})
end

--- League / cup rank per competition, matched on the exact stored name - as
--- the templates' join matched Football_Games.Competition = OriginalName.
local function competitionRanks()
	local ranks = {}
	local rows = mw.ext.cargo.query('Competitions',
		'OriginalName=name, League=league, Trophy=trophy', { limit = 500 })
	if #rows >= 500 then
		error('FootballSeasonTable: the competition catalogue reached 500 rows', 0)
	end
	for _, row in ipairs(rows) do
		local rank = OTHER
		if tonumber(row.league) == 1 then
			rank = LEAGUE
		elseif tonumber(row.trophy) == 1 then
			rank = CUP
		end
		ranks[row.name or ''] = rank
	end
	return ranks
end

--- Regroups rows within each season, keeping the seasons' own order.
local function ordered(rows, ranks)
	local result, group = {}, {}
	local function flush()
		table.sort(group, function(first, second)
			local firstRank = ranks[first.competition] or OTHER
			local secondRank = ranks[second.competition] or OTHER
			if firstRank ~= secondRank then
				return firstRank < secondRank
			end
			return first.competition < second.competition
		end)
		for _, row in ipairs(group) do
			result[#result + 1] = row
		end
		group = {}
	end
	for index, row in ipairs(rows) do
		if index > 1 and row.season ~= rows[index - 1].season then
			flush()
		end
		group[#group + 1] = row
	end
	flush()
	return result
end

--- `{{#קיים: target |[[target|text]] |text}}`.
local function linked(target, text)
	local title = mw.title.new(target)
	if title and title.exists then
		return '[[' .. target .. '|' .. text .. ']]'
	end
	return text
end

local function count(value)
	return tostring(tonumber(value) or 0)
end

local function row(entry)
	return '<div class="table-row">'
		.. '<span>' .. linked('עונת ' .. entry.season, entry.season) .. '</span>'
		.. '<span>' .. linked(entry.competition, entry.competition) .. '</span>'
		.. '<span>' .. count(entry.wins) .. '</span>'
		.. '<span>' .. count(entry.draws) .. '</span>'
		.. '<span>' .. count(entry.losses) .. '</span>'
		.. '</div>'
end

function p.rows(frame)
	local opponents = trim(frame.args['יריבות'])
	-- The query layer reads an empty filter as "no filter", which would list
	-- every game on the wiki. The template's IN ("") listed none: so do we.
	if opponents == '' then
		return ''
	end
	local rows = {}
	for _, entry in ipairs(pairs_({ ['יריבות'] = opponents })) do
		rows[#rows + 1] = {
			season = trim(entry.season),
			competition = trim(entry.competition),
			wins = entry.wins,
			draws = entry.draws,
			losses = entry.losses,
		}
	end
	local html = {}
	for _, entry in ipairs(ordered(rows, competitionRanks())) do
		html[#html + 1] = row(entry)
	end
	return table.concat(html, '\n')
end

return p
