--[[
Module:SeasonTable - the rows of a "season by season" table, for any sport.

Wiki page: Module:SeasonTable

A sport's opponent (and referee) pages list every (season, competition) pair
with the team's record in it. The templates did that with one #cargo_query for
the pairs and a row template that counted each result word again per row:
1 + kN queries, 84 rows on כדורסל:הפועל תל אביב. This renders the same rows
from TWO queries - the pairs with their counts, and the competition catalogue
for the order - whatever the sport.

    new(Queries, declaration, name)

`Queries` is the sport's binding of Module:SportQueries; `name` prefixes every
error. The declaration says what differs between sports, and nothing else:

    season, competition  the base table's two columns, as SQL
    results              the columns shown, left to right: { key, word }, where
                         `word` is a value of the `תוצאה` filter. Football shows
                         wins/draws/losses, basketball has no draw.
    catalogue            { table, name, league, trophy } - the competition list
                         that decides league before cup before the rest
    seasonLink           a format string for a season's page (`עונת %s`, or
                         `כדורסל: עונת %s`)
    competitionLink      a format string for a competition's page
    entities             the filters a table may be about; exactly one per call
    concentrated         optional { table, names, name } - the per-competition
                         grouping lookup the referee tables link through
                         (`קישור מפעל=מרכז`). Absent means the option is refused.

Three deliberate departures from the templates, decided 2026-09-22 for football
and kept for every sport:
  1. Every row. The templates set no limit, so Cargo's silent default of 100 cut
     the oldest seasons of the clubs with more pairs. (Basketball's largest is
     86 pairs, so nothing is cut there today - but it would be, silently, once
     הפועל ירושלים passes 100.) The query layer raises instead of truncating.
  2. Within a season: league first, then cup, then the rest, then by name.
     Seasons keep the database's `Season DESC`; only the rows inside one season
     are regrouped, which the templates left to MySQL.
  3. A competition with no catalogue row shows its real results. The templates
     counted through the catalogue and showed 0 for it.
]]

local SeasonTable = {}

local LEAGUE, CUP, OTHER = 1, 2, 3

local function trim(value)
	return mw.text.trim(value or '')
end

function SeasonTable.new(Queries, declaration, name)
	local NAME = name or 'SeasonTable'
	local p = {}

	--- One result column: how many of the group's games the word describes.
	--- The condition comes from the schema's own `תוצאה` choices, so the column
	--- and a filter by the same word cannot disagree.
	local function resultSum(word)
		return string.format('SUM(CASE WHEN %s THEN 1 ELSE 0 END)',
			Queries.choiceCondition('תוצאה', word))
	end

	--- The (season, competition) pairs with their results, in `Season DESC`.
	local function pairsOf(filters)
		local fields = {
			declaration.season .. '=season',
			declaration.competition .. '=competition',
		}
		for _, result in ipairs(declaration.results) do
			fields[#fields + 1] = resultSum(result.word) .. '=' .. result.key
		end
		return Queries.query(filters, {
			fields = table.concat(fields, ', '),
			groupBy = declaration.season .. ', ' .. declaration.competition,
			orderBy = declaration.season .. ' DESC',
			limit = declaration.limit,
		})
	end

	--- League / cup rank per competition, matched on the exact stored name - as
	--- the templates' join matched the games' competition against it.
	local function competitionRanks()
		local catalogue = declaration.catalogue
		local ranks = {}
		local rows = mw.ext.cargo.query(catalogue.table,
			string.format('%s=name, %s=league, %s=trophy',
				catalogue.name, catalogue.league, catalogue.trophy),
			{ limit = 500 })
		if #rows >= 500 then
			error(NAME .. ': the competition catalogue reached 500 rows', 0)
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

	--- Each competition's grouping name, by the referee rows' own lookup
	--- (`Names HOLDS name`, limit 1, no order) - run once per DISTINCT
	--- competition rather than once per row. Nine football names sit in two map
	--- rows (their own and a grouping row such as הליגה הראשונה בכדורגל), and
	--- which one that lookup returns follows how MySQL walks the HOLDS join. No
	--- rule over the map table reproduced that, so the lookup is the same.
	local function concentratedNames(rows)
		local map = declaration.concentrated
		if not map then
			error(NAME .. ': this sport declares no competition grouping map, '
				.. 'so קישור מפעל=מרכז has nothing to look up', 0)
		end
		local byName, distinct = {}, {}
		for _, entry in ipairs(rows) do
			if byName[entry.competition] == nil then
				byName[entry.competition] = ''
				distinct[#distinct + 1] = entry.competition
			end
		end
		table.sort(distinct)
		for _, competition in ipairs(distinct) do
			-- Refused rather than escaped: the templates never quoted this name
			-- either, and a stored competition carries no double quote.
			if competition:find('"', 1, true) or competition:find('&', 1, true) then
				error(NAME .. ': cannot look up the competition ' .. competition, 0)
			end
			local found = mw.ext.cargo.query(map.table, map.name .. '=concentrated', {
				where = map.names .. ' HOLDS "' .. competition .. '"', limit = 1 })
			byName[competition] = found[1] and trim(found[1].concentrated) or ''
		end
		return byName
	end

	--- The competition cell. Directly: `{{#קיים: C |[[C|C]] |C}}`. Through the
	--- map: `{{#קיים: X |[[X|C]] |X}}` with X the grouping name - so a missing
	--- page shows X, and a competition the map lacks shows nothing.
	local function competitionCell(competition, concentrated)
		if not concentrated then
			return linked(string.format(declaration.competitionLink, competition),
				competition)
		end
		local grouping = concentrated[competition] or ''
		local title = grouping ~= '' and mw.title.new(grouping) or nil
		if title and title.exists then
			return '[[' .. grouping .. '|' .. competition .. ']]'
		end
		return grouping
	end

	local function row(entry, concentrated)
		local cells = {
			'<span>' .. linked(string.format(declaration.seasonLink, entry.season),
				entry.season) .. '</span>',
			'<span>' .. competitionCell(entry.competition, concentrated) .. '</span>',
		}
		for _, result in ipairs(declaration.results) do
			cells[#cells + 1] = '<span>' .. count(entry[result.key]) .. '</span>'
		end
		return '<div class="table-row">' .. table.concat(cells) .. '</div>'
	end

	--- The rows of one table:
	---   {{#invoke:BasketballSeasonTable|rows|יריבות={{{יריבות לשליפה|}}}}}
	--- The section wrapper stays in the template, so its markup is the
	--- template's own; only the #cargo_query is replaced.
	function p.rows(frame)
		local filters, given = {}, 0
		for _, entity in ipairs(declaration.entities) do
			local value = trim(frame.args[entity])
			if value ~= '' then
				filters[entity] = value
				given = given + 1
			end
		end
		if given > 1 then
			error(string.format(NAME .. ': rows takes one of %s',
				table.concat(declaration.entities, ', ')), 0)
		end
		-- The query layer reads an empty filter as "no filter", which would list
		-- every game on the wiki. The templates' IN ("") listed none: so do we.
		if given == 0 then
			return ''
		end

		local rows = {}
		for _, entry in ipairs(pairsOf(filters)) do
			local kept = { season = trim(entry.season), competition = trim(entry.competition) }
			for _, result in ipairs(declaration.results) do
				kept[result.key] = entry[result.key]
			end
			rows[#rows + 1] = kept
		end

		local concentrated
		if trim(frame.args['קישור מפעל']) == 'מרכז' then
			concentrated = concentratedNames(rows)
		end
		local html = {}
		for _, entry in ipairs(ordered(rows, competitionRanks())) do
			html[#html + 1] = row(entry, concentrated)
		end
		return table.concat(html, '\n')
	end

	return p
end

return SeasonTable
