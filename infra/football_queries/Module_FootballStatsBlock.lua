--[[
Module:FootballStatsBlock - a statistics block from one query.

Wiki page: Module:FootballStatsBlock

Renders any block declared in Module:FootballStatsBlocks. The player events
block asks כמות אירועי שחקן for eight numbers one at a time - 32 queries for
the four tabs above it - and the day-results block asks כמות נתוני משחק for
six, on 366 calendar pages. Each asks once.

Template body, with the block named on the invoke:
    <includeonly>{{#invoke:FootballStatsBlock|block|בלוק=day-results}}</includeonly>

The output must be byte-identical to the template's, so the oddities are
reproduced deliberately and are marked where they are not obvious: the space
before "(" on the appearances row and its absence on the last one, the space
before ")" in "ספסולים )", and MediaWiki's own number formatting.
]]

local FootballQueries = require('Module:FootballQueries')

local DEFAULT_BLOCK = 'player-events'

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
			'FootballStatsBlock: the block has no cell named "%s"', name), 0)
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
	-- Half away from zero, as #expr rounds - not half up. Identical for the
	-- positive ratios this block shows, and wrong the day a signed statistic
	-- reuses it: #expr gives -0.15 for -29/200 where half-up gives -0.14.
	--
	-- The epsilon is not cosmetic either. MediaWiki rounds through PHP, which
	-- corrects for binary representation; Lua's floor does not. 29 goals in
	-- 200 appearances is 0.145, stored as slightly under, so the template
	-- printed 0.15 and this printed 0.14 - one of 26 diverging pairs under 700
	-- appearances.
	--
	-- It must stay this small. For a ratio of whole numbers g/a the distance
	-- to a .xx5 boundary is at least 1/(2a), so 1e-9 cannot move a value until
	-- roughly 5e8 appearances, while a coarser 1e-3 rounds 253/501 to 0.51
	-- where #expr says 0.5.
	-- Every ratio this block shows is non-negative, so the sign case is not
	-- handled - it is refused. Silently rounding a negative half-UP here would
	-- disagree with #expr, which rounds half away from zero (-0.145 is -0.15
	-- there and -0.14 with half-up), and a branch no input can reach is a
	-- branch no test can check. Whoever reuses this for a signed statistic has
	-- to add the sign deliberately.
	if value < 0 then
		error(string.format(
			'FootballStatsBlock: expression() is for non-negative ratios, '
			.. 'got %s - #expr rounds half away from zero and this does not',
			tostring(value)), 0)
	end

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

--- A summed column with nothing to sum: the template prints an empty cell,
--- because SUM over no rows is NULL where COUNT is 0.
formatters.plainOrEmpty = function(cells, row)
	local value = cells[row.cell]
	if value == nil then
		return ''
	end
	return integer(value)
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

--- Which block an #invoke asked for, and the only argument it may carry.
local function blockOf(frame)
	local name = DEFAULT_BLOCK
	for key, value in pairs(frame.args) do
		if key ~= 'בלוק' then
			error(string.format(
				'FootballStatsBlock: this entry point takes only בלוק, got "%s" '
				.. '- filters come from the calling template', tostring(key)), 0)
		end
		name = mw.text.trim(value)
	end

	local block = Blocks[name]
	if not block then
		error(string.format(
			'FootballStatsBlock: no block declared as "%s"', name), 0)
	end
	return name, block
end

local function renderRows(block, cells)
	-- Callers and tests may name the block instead of holding its declaration.
	if type(block) == 'string' then
		local named = Blocks[block]
		if not named then
			error(string.format(
				'FootballStatsBlock: no block declared as "%s"', block), 0)
		end
		block = named
	end

	-- Every row's cell must be one the block actually produces, checked before
	-- anything renders. Without this the check lives in need(), which cannot
	-- see the difference between a cell that was never declared and a summing
	-- cell whose value is legitimately NULL - so a typo between the two data
	-- pages would render an empty cell on all 366 day pages and look like a
	-- date with no games.
	local declared = {}
	for _, cell in ipairs(block.cells) do
		declared[cell.name] = true
	end
	for _, row in ipairs(block.rows) do
		if row.cell and not declared[row.cell] then
			error(string.format(
				'FootballStatsBlock: the block has no cell named "%s"',
				row.cell), 0)
		end
	end

	local lines = {}

	for index, row in ipairs(block.rows) do
		local formatter = formatters[row.format]
		if not formatter then
			error(string.format(
				'FootballStatsBlock: no formatter named "%s"', row.format), 0)
		end
		local shape = block.layout == 'stacked'
			and '<div class="Top10Row">\n<div class="Top10RowName">%s</div>\n'
				.. '<span class="Top10RowStat">%s</span></div>'
			or '<div class="Top10Row"><div class="Top10RowName">%s</div>'
				.. '<span class="Top10RowStat">%s</span></div>'
		lines[index] = string.format(shape, row.label, formatter(cells, row))
	end

	-- Two layouts, because the templates differ and the output must match
	-- them byte for byte: the player block puts a row on one line, the day
	-- block stacks the label and the value and separates rows with a blank
	-- line, ending with one.
	if block.layout == 'stacked' then
		return table.concat(lines, '\n\n') .. '\n'
	end
	return table.concat(lines, '\n')
end

--- The caller's parameters, plus whatever constant filters the block declares.
--- A block's constant filters are part of what the block IS, so a caller that
--- passes one of them is refused rather than silently overridden or silently
--- ignored. Either choice would leave a page showing the wrong window of
--- games with nothing to see in the wikitext.
local function sharedFilters(block, frame, parentArguments)
	local shared = parentArguments(frame)
	for name, value in pairs(block.filters or {}) do
		if shared[name] ~= nil and mw.text.trim(tostring(shared[name])) ~= '' then
			error(string.format(
				'FootballStatsBlock: %s is fixed by this block and cannot be '
				.. 'passed in', name), 0)
		end
		shared[name] = value
	end
	return shared
end

--- Reads the calling template's parameters, so nothing is forwarded by name
--- and nothing can be dropped. See the same guard in Module:FootballQueries.
---
--- It does not repeat blockOf's refusal of direct arguments: every entry point
--- that calls this has already been through blockOf, which accepts בלוק and
--- nothing else. A second copy of that guard here could never fire, and a
--- branch no input can reach is a branch no test can check.
local function parentArguments(frame)
	local filters = {}
	for name, value in pairs(frame:getParent().args) do
		filters[name] = value
	end
	return filters
end

local function block(frame)
	local _, declaration = blockOf(frame)
	local cells = FootballQueries.aggregate(
		sharedFilters(declaration, frame, parentArguments), declaration.cells)
	return renderRows(declaration, cells)
end

-- #vardefine variables live for the whole page parse and share one namespace
-- with every template on it, which already defines plain Hebrew names like
-- הופעות and שערים. So the names are prefixed and carry the entity, or a
-- second block on the same page - a comparison page, say - would overwrite the
-- first and the tabs would show the other player's numbers under the right
-- labels.
local VAR_PREFIX = 'FootballStatsBlock'

local function variableName(blockName, entity, tab)
	return string.format('%s/%s/%s/%s', VAR_PREFIX, blockName, entity, tab)
end

--- One cell of one tab, for a parent template that shows a number outside the
--- block itself.
local function cellVariableName(blockName, entity, tab, cell)
	return variableName(blockName, entity, tab) .. '/' .. cell
end

--- A cell as the templates print it: an integer, or nothing at all for a sum
--- with nothing to sum. Same rule as the plainOrEmpty formatter, because a
--- header and a row showing the same cell must not disagree.
local function valueText(value)
	if value == nil then
		return ''
	end
	return string.format('%d', math.floor(value + 0.5))
end

--- Every cell of the block, once per tab, as one flat list for one query.
---
--- The tab's category joins the cell's own conditions, so it lands inside the
--- CASE rather than the WHERE - which is what lets four OVERLAPPING categories
--- (רשמי contains the other three) share a single query. GROUP BY cannot
--- produce them.
local function cellsPerTab(block, tabs)
	local cells = {}
	for _, tab in ipairs(tabs) do
		for _, cell in ipairs(block.cells) do
			local filters = {}
			for name, value in pairs(cell.filters or {}) do
				filters[name] = value
			end
			filters['קטגוריית מפעל'] = tab
			cells[#cells + 1] = {
				name = tab .. '/' .. cell.name,
				filters = filters,
				grain = cell.grain,
				-- Carried through, or a summing cell quietly becomes a counting
				-- one and the goals column reads as a game count.
				sum = cell.sum,
			}
		end
	end
	return cells
end

--- The cells of one tab, pulled out of the merged result by their prefix.
local function cellsOfTab(block, values, tab)
	local tabCells = {}
	for _, cell in ipairs(block.cells) do
		tabCells[cell.name] = values[tab .. '/' .. cell.name]
	end
	return tabCells
end

--- Renders all four tabs from ONE query and stashes each in a page variable.
---
--- Called once, before the tab strip:
---   {{#invoke:FootballStatsBlock|prime}}
---
--- The strip itself is signed <shtml> whose hash is an HMAC under a per-wiki
--- secret, so it is never rebuilt - it stays in the template and this only
--- fills in what goes inside it. Eight cells times four overlapping
--- categories is 32 conditional aggregates in a single query, where the
--- template runs 32 queries.
local function prime(frame)
	local blockName, block = blockOf(frame)
	local shared = sharedFilters(block, frame, parentArguments)
	local entity = shared[block.entity]
	if not entity or mw.text.trim(entity) == '' then
		error(string.format(
			'FootballStatsBlock: prime needs %s to key its variables',
			block.entity), 0)
	end

	local values = FootballQueries.aggregate(
		shared, cellsPerTab(block, block.tabs))

	for _, tab in ipairs(block.tabs) do
		local tabCells = cellsOfTab(block, values, tab)
		for _, cell in ipairs(block.cells) do
			-- Each cell is stashed on its own as well as inside the rendered
			-- rows, because a parent template shows some of them outside the
			-- block: the day tabs are headed "ליגה (N משחקים)", and N is the
			-- games cell this query already computed. Without this the parent
			-- asks for those four counts in four more queries.
			frame:callParserFunction('#vardefine', {
				cellVariableName(blockName, entity, tab, cell.name),
				valueText(tabCells[cell.name]),
			})
		end
		frame:callParserFunction('#vardefine',
			{ variableName(blockName, entity, tab),
			  renderRows(block, tabCells) })
	end

	return ''
end

--- Reads one tab that prime already rendered:
---   {{#invoke:FootballStatsBlock|tab|קטגוריית מפעל=ליגה|שחקן={{{שחקן}}}}}
---
--- Raises when the variable is missing rather than rendering empty. An empty
--- block looks like a player with no record, which is the kind of silence this
--- layer exists to remove.
local function tab(frame)
	local blockName = mw.text.trim(frame.args['בלוק'] or DEFAULT_BLOCK)
	local declaration = Blocks[blockName]
	if not declaration then
		error(string.format(
			'FootballStatsBlock: no block declared as "%s"', blockName), 0)
	end

	local entity = frame.args[declaration.entity]
	local category = frame.args['קטגוריית מפעל']
	if not entity or not category then
		error(string.format('FootballStatsBlock: tab needs %s and קטגוריית מפעל',
			declaration.entity), 0)
	end

	local name = variableName(blockName, mw.text.trim(entity),
		mw.text.trim(category))
	local value = frame:callParserFunction('#var', { name })
	if not value or mw.text.trim(value) == '' then
		error(string.format(
			'FootballStatsBlock: nothing primed for %s - call '
			.. '{{#invoke:FootballStatsBlock|prime}} before the tab strip',
			name), 0)
	end
	return value
end

--- One number that prime already computed, for a parent template that shows it
--- outside the block:
---   {{#invoke:FootballStatsBlock|value|בלוק=day-results|תא=games
---     |קטגוריית מפעל=ליגה|תאריך={{{תאריך|}}}}}
---
--- The day tab headers read "ליגה (N משחקים)", and N is the block's own games
--- cell. Reading it from the primed query is what takes a day page from eight
--- queries to one; asking for it separately would put four of them back.
local function value(frame)
	local blockName = mw.text.trim(frame.args['בלוק'] or DEFAULT_BLOCK)
	local declaration = Blocks[blockName]
	if not declaration then
		error(string.format(
			'FootballStatsBlock: no block declared as "%s"', blockName), 0)
	end

	local entity = frame.args[declaration.entity]
	local category = frame.args['קטגוריית מפעל']
	local cell = frame.args['תא']
	if not entity or not category or not cell then
		error(string.format(
			'FootballStatsBlock: value needs %s, קטגוריית מפעל and תא',
			declaration.entity), 0)
	end
	cell = mw.text.trim(cell)

	local declared = false
	for _, entry in ipairs(declaration.cells) do
		declared = declared or entry.name == cell
	end
	if not declared then
		error(string.format(
			'FootballStatsBlock: block "%s" has no cell named "%s"',
			blockName, cell), 0)
	end

	-- An empty cell is a legitimate answer (a sum with nothing to sum), so
	-- whether prime ran is decided by the tab's own variable, never by this
	-- one being empty.
	local primed = frame:callParserFunction('#var', {
		variableName(blockName, mw.text.trim(entity), mw.text.trim(category)),
	})
	if not primed or mw.text.trim(primed) == '' then
		error(string.format(
			'FootballStatsBlock: nothing primed for %s/%s - call '
			.. '{{#invoke:FootballStatsBlock|prime|בלוק=%s}} first',
			mw.text.trim(entity), mw.text.trim(category), blockName), 0)
	end

	return frame:callParserFunction('#var', {
		cellVariableName(blockName, mw.text.trim(entity),
			mw.text.trim(category), cell),
	})
end

--- The body of a <tabber>: one `label=content` per tab, separated by `|-|`.
---
--- Tabber splits the body on `|-|` and each tab on its FIRST `=`, and neither
--- is escapable, so a label carrying either character would spill the rest of
--- itself into the panel. That is not hypothetical - it is how the old strips'
--- `class="fas fa-home"` labels broke when they were first converted - so the
--- labels are refused here rather than mangled on 366 pages.
local function tabberOf(tabStrip, panelOf)
	local parts = {}
	for _, tab in ipairs(tabStrip) do
		if tab.label:find('=', 1, true) or tab.label:find('|', 1, true) then
			error(string.format(
				'FootballStatsBlock: the tab label "%s" contains = or |, which '
				.. 'tabber uses as separators', tab.label), 0)
		end
		parts[#parts + 1] = string.format('%s%s=%s',
			#parts == 0 and '' or '|-|', tab.label, panelOf(tab))
	end
	return table.concat(parts)
end

local function tabberBody(block, values)
	local heading = block.tabHeading
	if not heading then
		error('FootballStatsBlock: a block with a tabStrip must declare '
			.. 'tabHeading', 0)
	end
	local declared = {}
	for _, cell in ipairs(block.cells) do
		declared[cell.name] = true
	end
	if not declared[heading.cell] then
		error(string.format(
			'FootballStatsBlock: the block has no cell named "%s"',
			heading.cell), 0)
	end

	return tabberOf(block.tabStrip, function(entry)
		local tabCells = cellsOfTab(block, values, entry.category)
		return string.format(heading.format, entry.heading,
				valueText(tabCells[heading.cell]))
			.. '\n' .. renderRows(block, tabCells)
	end)
end

--- The whole widget - tab strip, headings and all four panels - from ONE query
--- and ONE #invoke:
---   {{#invoke:FootballStatsBlock|render|בלוק=day-results}}
---
--- This is what prime/tab/value collapse into. Those three exist because the
--- tab strip was signed <shtml> that could not be rebuilt, so the numbers had
--- to be handed across #invoke boundaries through page variables: five invokes
--- per page, four of them reading back what the first had stashed. Emitting the
--- strip as a <tabber> removes the boundary, and with it the variables, the
--- namespace they shared with every other template on the page, and the
--- "nothing primed" failure mode.
local function render(frame)
	local blockName, declaration = blockOf(frame)
	if not declaration.tabStrip then
		error(string.format(
			'FootballStatsBlock: block "%s" declares no tabStrip, so there is '
			.. 'nothing to render as tabs', blockName), 0)
	end

	local tabs = {}
	for index, entry in ipairs(declaration.tabStrip) do
		tabs[index] = entry.category
	end

	local values = FootballQueries.aggregate(
		sharedFilters(declaration, frame, parentArguments),
		cellsPerTab(declaration, tabs))

	-- The wrapper is what the skin hangs the tab icons and the strip's spacing
	-- on. Without it these tabs would pick up the bare TabberNeue look, and
	-- with an unscoped stylesheet every other tabber on the wiki would pick up
	-- this one's.
	return '<div class="tabber-converted">'
		.. frame:extensionTag('tabber', tabberBody(declaration, values))
		.. '</div>'
end

--- The "עוד" link for one tab: Cargo's own ViewData page, showing rows 11-110
--- of that tab's ranking, as the templates' `more results text` link does.
--- The query is compiled by FootballQueries.build from the tab's own filters,
--- so the link and the numbers cannot disagree about what is being counted.
local function moreLink(declaration, filters)
	local query = FootballQueries.build(filters)
	local key = FootballQueries.groupKeyColumn(declaration.groupBy)
	local url = mw.uri.fullUrl('מיוחד:ViewData', {
		tables = query.tables,
		join_on = query.join,
		where = query.where,
		fields = key .. ', COUNT(*)',
		group_by = key,
		order_by = 'COUNT(*) DESC, ' .. key,
		format = 'template',
		template = declaration.rowTemplate,
		offset = tostring(declaration.top),
		limit = '100',
	})
	-- Inside a div on one line. On its own line the external link is wrapped
	-- in a <p> - a paragraph margin the templates' raw Cargo link never had -
	-- and the parser leaves an empty <p> beside the panel, which shifted
	-- :nth-child counting and silently disabled the panel fade.
	return string.format('<div>[%s %s]</div>', tostring(url), declaration.moreText)
end

--- Four leaderboard boxes, each a tabber, from ONE query:
---   {{#invoke:FootballStatsBlock|leaderboards|בלוק=referee-assistant|שופט=…}}
---
--- Its own argument contract, unlike `render`: the block's entity argument is
--- passed directly and nothing is read from the calling template. The referee
--- section's caller carries שם להצגה and הסתר הערת סוג עמוד, neither of which is
--- a filter, so reading them would raise; passing the name explicitly is the
--- only way the right name reaches the query.
local function leaderboards(frame)
	local blockName = mw.text.trim(frame.args['בלוק'] or '')
	local declaration = Blocks[blockName]
	if not declaration or not declaration.boxes then
		error(string.format(
			'FootballStatsBlock: no leaderboard block declared as "%s"',
			blockName), 0)
	end
	for key in pairs(frame.args) do
		if key ~= 'בלוק' and key ~= declaration.entity then
			error(string.format(
				'FootballStatsBlock: leaderboards takes only בלוק and %s, got "%s"',
				declaration.entity, tostring(key)), 0)
		end
	end

	-- An empty name is refused, never passed on: the query layer reads an
	-- empty filter as "no filter", so the page would rank every player in
	-- every game under this referee's name.
	local entity = mw.text.trim(frame.args[declaration.entity] or '')
	if entity == '' then
		error(string.format(
			'FootballStatsBlock: leaderboards needs a non-empty %s',
			declaration.entity), 0)
	end

	local shared = {}
	for name, value in pairs(declaration.shared or {}) do
		shared[name] = value
	end
	shared[declaration.entityFilter] = entity

	local columns = {}
	for _, box in ipairs(declaration.boxes) do
		for _, tab in ipairs(declaration.tabStrip) do
			local filters = {}
			for name, value in pairs(box.filters) do
				filters[name] = value
			end
			filters['קטגוריית מפעל'] = tab.category
			columns[#columns + 1] = {
				name = box.key .. '/' .. tab.category,
				grain = 'event',
				filters = filters,
			}
		end
	end

	local results = FootballQueries.leaderboard(shared, columns,
		{ groupBy = declaration.groupBy, top = declaration.top })

	local out = {}
	for _, box in ipairs(declaration.boxes) do
		local body = tabberOf(declaration.tabStrip, function(tab)
			local result = results[box.key .. '/' .. tab.category]

			local lines = { string.format(declaration.tabHeading, tab.heading,
				result.players, box.noun) }
			for _, row in ipairs(result.rows) do
				lines[#lines + 1] = frame:expandTemplate{
					title = declaration.rowTemplate,
					args = { row.name, tostring(row.count) },
				}
			end
			if result.more then
				-- The link's query is the tab's full filter set: the shared
				-- ones, the referee, the box's events and the tab's category.
				local filters = {}
				for name, value in pairs(shared) do
					filters[name] = value
				end
				for name, value in pairs(box.filters) do
					filters[name] = value
				end
				filters['קטגוריית מפעל'] = tab.category
				lines[#lines + 1] = moreLink(declaration, filters)
			end

			return table.concat(lines, '\n')
		end)

		out[#out + 1] = table.concat({
			'<div class="records-list-tabs-container" id="שיאנים">',
			string.format('<div class="title">%s</div>', box.title),
			'<div class="list"><div class="tabber-converted">'
				.. frame:extensionTag('tabber', body)
				.. '</div></div>',
			'</div>',
		}, '\n')
	end
	return table.concat(out, '\n')
end

return {
	leaderboards = leaderboards,
	block = block,
	prime = prime,
	tab = tab,
	value = value,
	render = render,
	-- Exposed for the test suite, which asserts the HTML without a frame.
	renderRows = renderRows,
	tabberBody = tabberBody,
}
