--[[
Module:FootballPlayerEvents - a player's events block from one query.

Wiki page: Module:FootballPlayerEvents

Replaces תבנית:סטטיסטיקה/תצוגה/שחקנים/סיכום אירועים לפי מפעל, which asks
כמות אירועי שחקן for eight numbers one at a time - 32 queries for the four
tabs above it. This asks once.

Template body:
    <includeonly>{{#invoke:FootballPlayerEvents|block}}</includeonly>

The output must be byte-identical to the template's, so the oddities are
reproduced deliberately and are marked where they are not obvious: the space
before "(" on the appearances row and its absence on the last one, the space
before ")" in "ספסולים )", and MediaWiki's own number formatting.
]]

local FootballQueries = require('Module:FootballQueries')

local BLOCK = 'player-events'

--- Copies a table out of an mw.loadData proxy.
---
--- mw.loadData does not return a plain table: it returns a proxy whose fields
--- are served through a metatable, so `#` reports 0 and `ipairs` stops at the
--- first element however many there are. Measured in Scribunto - the block
--- rendered "aggregate needs at least one cell" while the data page held
--- eight. Key lookups work, `pairs` works, lengths do not, so the arrays are
--- materialised once here.
---
--- The page is still read with loadData, so it is parsed once per page rather
--- than once per #invoke; only this copy is per call, and it is eight rows.
local function materialise(value)
	if type(value) ~= 'table' then
		return value
	end
	local copy = {}
	for key, entry in pairs(value) do
		copy[key] = materialise(entry)
	end
	return copy
end

local Blocks = materialise(mw.loadData('Module:FootballStatsBlocks'))

--- The value of a cell the block declared, or an error.
---
--- A nil here means the row data names a cell the cell list does not produce -
--- a typo between two data pages. Defaulting it to 0 would print a plausible
--- number for a broken block, which is the failure this layer exists to avoid.
local function need(cells, name)
	local value = cells[name]
	if value == nil then
		error(string.format(
			'FootballPlayerEvents: the block has no cell named "%s"', name), 0)
	end
	return value
end

--- An integer the way the template prints one.
local function integer(value)
	return string.format('%d', math.floor(value + 0.5))
end

--- A number the way {{#חשב: … round 2}} prints one: half away from zero, and
--- trailing zeros omitted, so 0.5 is "0.5" and 1 is "1" rather than "1.00".
local function expression(value)
	-- The epsilon is not cosmetic. MediaWiki's #expr rounds through PHP, which
	-- corrects for binary representation; Lua's floor does not. 29 goals in 200
	-- appearances is 0.145, stored as slightly under, so the template printed
	-- 0.15 and this printed 0.14 - one of 26 diverging pairs under 700
	-- appearances, 23/40 among them.
	local rounded = math.floor(value * 100 + 0.5 + 1e-9) / 100
	local text = string.format('%.2f', rounded)
	if text:find('%.') then
		text = text:gsub('0+$', ''):gsub('%.$', '')
	end
	return text
end

local formatters = {}

formatters.plain = function(cells, row)
	return integer(need(cells, row.cell))
end

formatters.appearancesWithSubstitutions = function(cells)
	return string.format('%s (%s חילופים)',
		integer(need(cells, 'appearances')),
		integer(need(cells, 'substitutions')))
end

formatters.goalsWithRatio = function(cells)
	local appearances = need(cells, 'appearances')
	local goals = need(cells, 'goals')

	-- The template guards division by zero with #שווה and prints a bare 0 in
	-- that branch - not 0.00, and not 0.0.
	local ratio = '0'
	if appearances ~= 0 then
		ratio = expression(goals / appearances)
	end
	return string.format('%s (%s שערים למשחק, %s פנדלים)',
		integer(goals), ratio, integer(need(cells, 'penaltyGoals')))
end

formatters.benchStartsWithBenchings = function(cells)
	-- No space before "(" here, and one before ")", exactly as the template
	-- emits it. Both are load bearing for a byte-identical comparison.
	local benchStarts = need(cells, 'benchStarts')
	local benchings = benchStarts - need(cells, 'substitutions')
	return string.format('%s(%s ספסולים )',
		integer(benchStarts), integer(benchings))
end

local function renderRows(cells)
	local block = Blocks[BLOCK]
	local lines = {}

	for index, row in ipairs(block.rows) do
		local formatter = formatters[row.format]
		if not formatter then
			error(string.format(
				'FootballPlayerEvents: no formatter named "%s"', row.format), 0)
		end
		lines[index] = string.format(
			'<div class="Top10Row"><div class="Top10RowName">%s</div>'
			.. '<span class="Top10RowStat">%s</span></div>',
			row.label, formatter(cells, row))
	end

	return table.concat(lines, '\n')
end

--- Reads the calling template's parameters, so nothing is forwarded by name
--- and nothing can be dropped. See the same guard in Module:FootballQueries.
local function parentArguments(frame)
	local direct = false
	for _ in pairs(frame.args) do
		direct = true
		break
	end
	if direct then
		error('FootballPlayerEvents: block reads the calling template\'s '
			.. 'parameters and takes none of its own - put it in a template '
			.. 'body as {{#invoke:FootballPlayerEvents|block}}', 0)
	end

	local filters = {}
	for name, value in pairs(frame:getParent().args) do
		filters[name] = value
	end
	return filters
end

local function block(frame)
	local cells = FootballQueries.aggregate(
		parentArguments(frame), Blocks[BLOCK].cells)
	return renderRows(cells)
end

-- #vardefine variables live for the whole page parse and share one namespace
-- with every template on it, which already defines plain Hebrew names like
-- הופעות and שערים. So the names are prefixed and carry the entity, or a
-- second block on the same page - a comparison page, say - would overwrite the
-- first and the tabs would show the other player's numbers under the right
-- labels.
local VAR_PREFIX = 'FootballPlayerEvents'

local function variableName(entity, tab)
	return string.format('%s/%s/%s', VAR_PREFIX, entity, tab)
end

--- Renders all four tabs from ONE query and stashes each in a page variable.
---
--- Called once, before the tab strip:
---   {{#invoke:FootballPlayerEvents|prime}}
---
--- The strip itself is signed <shtml> whose hash is an HMAC under a per-wiki
--- secret, so it is never rebuilt - it stays in the template and this only
--- fills in what goes inside it. Eight cells times four overlapping
--- categories is 32 conditional aggregates in a single query, where the
--- template runs 32 queries.
local function prime(frame)
	local shared = parentArguments(frame)
	local entity = shared['שחקן']
	if not entity or mw.text.trim(entity) == '' then
		error('FootballPlayerEvents: prime needs שחקן to key its variables', 0)
	end

	local block = Blocks[BLOCK]
	local cells = {}
	for _, tab in ipairs(block.tabs) do
		for _, cell in ipairs(block.cells) do
			local filters = {}
			for name, value in pairs(cell.filters or {}) do
				filters[name] = value
			end
			-- The tab's category joins the cell's own conditions, so it lands
			-- inside the CASE rather than the WHERE - which is what lets four
			-- overlapping categories share one query.
			filters['קטגוריית מפעל'] = tab
			cells[#cells + 1] = {
				name = tab .. '/' .. cell.name,
				filters = filters,
				grain = cell.grain,
			}
		end
	end

	local values = FootballQueries.aggregate(shared, cells)

	for _, tab in ipairs(block.tabs) do
		local tabCells = {}
		for _, cell in ipairs(block.cells) do
			tabCells[cell.name] = values[tab .. '/' .. cell.name]
		end
		frame:callParserFunction('#vardefine',
			{ variableName(entity, tab), renderRows(tabCells) })
	end

	return ''
end

--- Reads one tab that prime already rendered:
---   {{#invoke:FootballPlayerEvents|tab|קטגוריית מפעל=ליגה|שחקן={{{שחקן}}}}}
---
--- Raises when the variable is missing rather than rendering empty. An empty
--- block looks like a player with no record, which is the kind of silence this
--- layer exists to remove.
local function tab(frame)
	local entity = frame.args['שחקן']
	local category = frame.args['קטגוריית מפעל']
	if not entity or not category then
		error('FootballPlayerEvents: tab needs שחקן and קטגוריית מפעל', 0)
	end

	local name = variableName(mw.text.trim(entity), mw.text.trim(category))
	local value = frame:callParserFunction('#var', { name })
	if not value or mw.text.trim(value) == '' then
		error(string.format(
			'FootballPlayerEvents: nothing primed for %s - call '
			.. '{{#invoke:FootballPlayerEvents|prime}} before the tab strip',
			name), 0)
	end
	return value
end

return {
	block = block,
	prime = prime,
	tab = tab,
	-- Exposed for the test suite, which asserts the HTML without a frame.
	renderRows = renderRows,
}
