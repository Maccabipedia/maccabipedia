--[[
Module:FootballQueries - one Cargo query from one filter set.

Wiki page: Module:FootballQueries

The football statistics templates issue one Cargo query per number: a player's
events block runs eight, times four tabs. Each of those queries re-implements
the same join graph, quote rules and competition flags, and they have drifted
apart. This module owns them once, so a display module can render a whole block
from a single query.

Filter names arrive in Hebrew - they are the templates' published contract, and
the values are Hebrew data. Query options (limit, fields, groupBy) are English,
because they are this code's own interface. Nothing else here is Hebrew.

Two rules this module exists to enforce, both of which have shipped as wrong
numbers before:

  * An unsupported filter is an error, never a dropped condition. A filter that
    is silently ignored does not look like a failure, it looks like a number -
    an opponent page once asked for its own yellow cards and was handed the
    wiki-wide total.
  * A result that reached the row limit is an error, never a short answer.
    Cargo truncates without warning, and a leaderboard built from a truncated
    result is a normal-looking table of wrong numbers.
]]

local FootballQueries = {}

local Fields = mw.loadData('Module:FootballQueries/Fields')

-- {{PAGENAME}} and friends deliver quote characters HTML-encoded, so a name
-- arrives as either the literal character or an entity. Normalise before any
-- decision about quoting is made.
local ENTITIES = {
	['&#34;'] = '"',
	['&#x22;'] = '"',
	['&#X22;'] = '"',
	['&quot;'] = '"',
	['&#39;'] = "'",
	['&#x27;'] = "'",
	['&#X27;'] = "'",
	['&apos;'] = "'",
}

--- Decodes the quote spellings, then refuses anything still carrying an
--- ampersand.
---
--- This is load bearing, not tidiness. CargoSQLQuery::newFromValues runs
--- htmlspecialchars_decode(whereStr, ENT_QUOTES) on the WHERE clause AFTER
--- this module has quoted and escaped it, and that path is shared by
--- CargoLuaLibrary. So any entity spelling this table does not know survives
--- escaping, reaches Cargo, and is turned back into a raw quote INSIDE the
--- SQL. Proven read-only against production: a value of
---   x&#x22; OR 1=1 OR &#x22;
--- returned every row in the table instead of raising - the wiki-wide-total
--- bug, reappearing inside the module written to prevent it.
---
--- Refusing a surviving ampersand is safe rather than restrictive: no value in
--- any quote-bearing column on production contains one (LIKE '%&%' -> 0 rows),
--- so a name that needs it does not exist, while a query that smuggles one is
--- always a mistake or an attack.
local function normalise(value)
	value = tostring(value)
	for entity, character in pairs(ENTITIES) do
		value = value:gsub(entity, character)
	end
	value = mw.text.trim(value)

	if value:find('&', 1, true) then
		error(string.format(
			'FootballQueries: value contains an ampersand, which Cargo would '
			.. 'decode inside the query: %s', value), 0)
	end

	return value
end

local function quoteRuleFor(column)
	local rule = Fields.columns[column]
	if not rule then
		-- A guess here is the §16 trap: query a stripped column with a raw name
		-- and you get zero rows and no error.
		error(string.format(
			'FootballQueries: no quote rule declared for column %s', column), 0)
	end
	return rule
end

--- One SQL literal, quoted according to how the target stores quote characters.
--- `label` only names the offender in error messages.
local function literalByRule(rule, label, value)
	local column = label
	value = normalise(value)

	if rule == 'number' then
		local number = tonumber(value)
		if not number then
			error(string.format(
				'FootballQueries: %s expects a number, got "%s"', column, value), 0)
		end
		return tostring(number)
	end

	if rule == 'strip' then
		-- No stored value in this column contains a quote character, so a name
		-- carrying one must be stripped to match.
		value = value:gsub('"', ''):gsub("'", '')
	end

	-- Escape rather than refuse. Opponents.OriginalName really does store a
	-- literal double quote (בית"ר ירושלים), so refusing one made every Beitar
	-- query a hard error. Backslash first, or it would double-escape the
	-- backslashes this adds.
	value = value:gsub('\\', '\\\\'):gsub('"', '\\"')

	return '"' .. value .. '"'
end

--- One SQL literal for one declared column.
local function literal(column, value)
	return literalByRule(quoteRuleFor(column), column, value)
end

local function splitList(value)
	local items = {}
	for item in tostring(value):gmatch('[^,]+') do
		item = mw.text.trim(item)
		if item ~= '' then
			items[#items + 1] = item
		end
	end
	return items
end

local function tableOf(column)
	local tableName = column:match('^([^.]+)%.')
	if not tableName or not Fields.tables[tableName] then
		error(string.format(
			'FootballQueries: column %s belongs to no known table', column), 0)
	end
	return tableName
end

--- Collects WHERE conditions and the tables they require.
local Builder = {}
Builder.__index = Builder

local function newBuilder()
	return setmetatable({ conditions = {}, tables = { Football_Games = true } }, Builder)
end

function Builder:needs(column)
	self.tables[tableOf(column)] = true
end

function Builder:add(condition)
	self.conditions[#self.conditions + 1] = condition
end

function Builder:addComparison(column, operator, value)
	self:needs(column)
	self:add(string.format('%s %s %s', column, operator, literal(column, value)))
end

function Builder:addIn(column, values)
	self:needs(column)
	local literals = {}
	for index, value in ipairs(values) do
		literals[index] = literal(column, value)
	end
	if #literals == 0 then
		-- IN () is a SQL error, and an empty alias expansion means the name
		-- matched nothing - say so instead of emitting a broken query.
		error(string.format(
			'FootballQueries: no values to match for %s', column), 0)
	end
	self:add(string.format('%s IN (%s)', column, table.concat(literals, ', ')))
end

--- Runs one Cargo query and refuses a truncated answer.
---
--- mw.ext.cargo.query reaches CargoSQLQuery::run directly, so unlike
--- #cargo_query it never enters CargoQuery.php - no second LIMIT-less SELECT
--- and none of the cargo_backlinks writes a page view otherwise performs.
local function runCargo(tables, fields, options)
	-- A limit that came from wikitext is a string, and "500" > 5000 compares a
	-- string with a number and raises. Coerce before any comparison.
	if options.limit ~= nil then
		local limit = tonumber(options.limit)
		if not limit then
			error(string.format(
				'FootballQueries: הגבלה must be a number, got "%s"',
				tostring(options.limit)), 0)
		end
		options.limit = math.floor(limit)
	end
	options.limit = options.limit or Fields.defaultLimit
	if options.limit > Fields.maxLimit then
		error(string.format(
			'FootballQueries: limit %d exceeds maxLimit %d',
			options.limit, Fields.maxLimit), 0)
	end

	local rows = mw.ext.cargo.query(tables, fields, options)

	if #rows >= options.limit then
		-- Cargo truncates silently. A block built from a cut-off result is a
		-- normal-looking table of wrong numbers, so this is fatal.
		error(string.format(
			'FootballQueries: query returned %d rows and hit the limit of %d - '
			.. 'raise the limit or narrow the query', #rows, options.limit), 0)
	end

	return rows
end

--- Every name a stadium or a club is stored under, for the one that was asked
--- for. One stadium has several names and a club changes its name across eras,
--- so a filter on either has to become an IN over all of them.
local function expandAliases(kind, value)
	local spec = Fields.aliases[kind]
	local rows = runCargo(spec.tables, spec.returnColumn .. '=name', {
		join = spec.join,
		where = spec.matchColumn .. ' = '
			.. literalByRule(spec.matchQuotes, spec.matchColumn, value),
		limit = Fields.defaultLimit,
	})

	local names = {}
	for index, row in ipairs(rows) do
		-- Returned as-is: the caller matches these against a declared column,
		-- and that column's own quote rule decides whether they are stripped.
		names[index] = row.name
	end
	if #names == 0 then
		error(string.format(
			'FootballQueries: %s "%s" matched no known name', kind, value), 0)
	end
	return names
end

-- MySQL format strings are interpolated into SQL, so only date-format
-- characters are allowed through.
local SAFE_DATE_FORMAT = '^[%%%a%d%-/:%. ]+$'

local handlers = {}

handlers.text = function(builder, spec, value)
	builder:addComparison(spec.column, '=', value)
end

handlers.number = handlers.text

handlers.numberNotEqual = function(builder, spec, value)
	builder:addComparison(spec.column, '!=', value)
end

handlers.list = function(builder, spec, value)
	builder:addIn(spec.column, splitList(value))
end

handlers.numberList = handlers.list

handlers.holds = function(builder, spec, value)
	builder:needs(spec.column)
	builder:add(string.format(
		'%s HOLDS %s', spec.column, literal(spec.column, value)))
end

handlers.maccabiSide = function(builder, spec, value)
	-- מכבי=לא asks for the opponent's events; anything else means Maccabi's.
	builder:addComparison(spec.column, '=', normalise(value) == 'לא' and 0 or 1)
	builder.teamConstrained = true
end

handlers.resultWord = function(builder, spec, value)
	local resultOpt = Fields.resultWords[normalise(value)]
	if not resultOpt then
		error(string.format(
			'FootballQueries: תוצאה must be ניצחון, תיקו or הפסד, got "%s"',
			value), 0)
	end
	builder:addComparison(spec.column, '=', resultOpt)
end

handlers.competitionCategory = function(builder, _, value)
	local condition = Fields.competitionCategories[normalise(value)]
	if not condition then
		error(string.format(
			'FootballQueries: unknown קטגוריית מפעל "%s"', value), 0)
	end
	builder.tables.Competitions = true
	builder:add(condition)
end

handlers.stadiumAliases = function(builder, spec, value)
	builder:addIn(spec.column, expandAliases('stadium', value))
end

handlers.opponentAliases = function(builder, spec, value)
	builder:addIn(spec.column, expandAliases('opponent', value))
end

handlers.date = function(builder, spec, value, filters)
	local format = filters['פורמט תאריך']
	format = (format and mw.text.trim(format) ~= '') and mw.text.trim(format)
		or '%d-%m-%Y'
	-- Real call sites pass the format WITH its quotes, because the template
	-- interpolated it straight into the SQL and its own default was quoted:
	-- ימים/סיכום תוצאות sends פורמט תאריך="%d-%m". Accept either form and quote
	-- exactly once, or every one of those call sites is a Scribunto error.
	format = format:gsub('^"(.*)"$', '%1'):gsub("^'(.*)'$", '%1')
	if not format:match(SAFE_DATE_FORMAT) then
		error(string.format(
			'FootballQueries: unsafe פורמט תאריך "%s"', format), 0)
	end

	builder:needs(spec.column)
	-- The templates interpolate the date unquoted, which MySQL reads as
	-- arithmetic; it is quoted here.
	builder:add(string.format(
		'DATE_FORMAT(%s, "%s") = DATE_FORMAT(%s, "%s")',
		literal(spec.column, value), format, spec.column, format))
end

-- Consumed by another handler, contributes no condition of its own.
handlers.modifier = function() end

--- Runs the handlers for one filter set and returns the builder.
---
--- `skipDefaults` leaves out row-level defaults such as the Team constraint.
--- The merge needs that: a cell's own conditions go into the FIELDS as a
--- conditional aggregate, and a row-level default belongs in the WHERE once,
--- not repeated inside every cell.
local function buildInto(filters, skipDefaults)
	local builder = newBuilder()

	-- Sorted, so the same filter set always produces byte-identical SQL: it
	-- keeps the generated query diffable and comparable between runs.
	local names = {}
	for name in pairs(filters) do
		if type(name) ~= 'string' then
			-- A positional parameter, or a trailing pipe in the template call,
			-- arrives as a number key. Sorting mixed keys dies inside table.sort
			-- with "attempt to compare string with number", which tells a page
			-- author nothing.
			error(string.format(
				'FootballQueries: positional parameter %s - every filter must be '
				.. 'named', tostring(name)), 0)
		end
		names[#names + 1] = name
	end
	table.sort(names)

	for _, name in ipairs(names) do
		local value = filters[name]
		local spec = Fields.filters[name]
		if not spec then
			-- The guard. A wrapper that forwards a fixed parameter list defeats
			-- it, so wrappers must forward everything they were given.
			error(string.format(
				'FootballQueries: unsupported filter "%s"', name), 0)
		end
		-- Templates pass every parameter whether or not it was set, so an empty
		-- value means "not provided" rather than "match the empty string".
		if value ~= nil and mw.text.trim(tostring(value)) ~= '' then
			handlers[spec.kind](builder, spec, value, filters)
		end
	end

	-- Every query template that touches Games_Events constrains Team: most
	-- hardcode `AND Team = 1`, the rest default the מכבי parameter to it. So an
	-- events query without it is not "unfiltered", it is wrong - it counts the
	-- opponent's events too. Measured: a league goals count for one player
	-- returns 152 without this and 150 with it, because two rows on that page
	-- belong to the opposing side.
	if builder.tables.Games_Events and not builder.teamConstrained
			and not skipDefaults then
		builder:addComparison('Games_Events.Team', '=', 1)
	end

	return builder
end

--- Turns a builder's tables into the tables and join of a query.
local function tablesAndJoin(builder)
	local joined = {}
	for name in pairs(builder.tables) do
		if name ~= 'Football_Games' then
			joined[#joined + 1] = name
		end
	end
	table.sort(joined)

	-- Only the tables the filters actually reached. Cargo's join on is a LEFT
	-- JOIN, so omitting an unused table cannot change a row count.
	local tableNames = { 'Football_Games' }
	local joins = {}
	for _, name in ipairs(joined) do
		tableNames[#tableNames + 1] = name
		joins[#joins + 1] = Fields.tables[name].join
	end

	return table.concat(tableNames, ','), table.concat(joins, ',')
end

local function whereOf(builder)
	return #builder.conditions > 0
		and table.concat(builder.conditions, ' AND ') or '1=1'
end

--- Turns a filter set into the tables, join and where of one query.
function FootballQueries.build(filters)
	local builder = buildInto(filters)
	local tables, join = tablesAndJoin(builder)
	return { tables = tables, join = join, where = whereOf(builder) }
end

--- Every cell of a block from ONE query.
---
--- `shared` are the filters the whole block has in common (the player, the
--- competition category). `cells` is a list of
---   { name = 'goals', filters = { … }, grain = 'event' | 'game' }
--- and each cell's own filters become a conditional aggregate in the SELECT
--- rather than a second query. The block that motivates this runs 8 queries
--- per tab and 32 per page; this is 1.
---
--- Two things the merge has to get right, and neither is optional:
---
---  * **Row-level conditions stay in the WHERE.** The Team constraint and the
---    join set are derived from the union of every cell's filters, so a
---    condition that belongs to the whole row set is applied once, and a table
---    only a cell mentions is still joined. Deriving them from the shared
---    filters alone silently drops both.
---  * **Grain is declared, not guessed.** Joining Games_Events multiplies a
---    game into one row per event - up to 43x, measured. So a cell counting
---    events sums rows, while a cell counting games must count DISTINCT game
---    pages. Mixing the two without saying so inflates the game cell by the
---    number of events, which looks like a plausible number.
function FootballQueries.aggregate(shared, cells, options)
	options = options or {}
	if #cells == 0 then
		error('FootballQueries: aggregate needs at least one cell', 0)
	end

	-- The union decides what is joined and whether Team must be constrained.
	local union = {}
	for name, value in pairs(shared) do
		union[name] = value
	end
	for _, cell in ipairs(cells) do
		for name, value in pairs(cell.filters or {}) do
			union[name] = value
		end
	end

	local unionBuilder = buildInto(union)
	local tables, join = tablesAndJoin(unionBuilder)

	-- The WHERE carries the shared filters plus the row-level default, which
	-- buildInto adds when the union reaches Games_Events.
	local sharedBuilder = buildInto(shared, true)
	if unionBuilder.tables.Games_Events and not sharedBuilder.teamConstrained then
		sharedBuilder:addComparison('Games_Events.Team', '=', 1)
	end

	local fields = {}
	local aliases = {}
	for index, cell in ipairs(cells) do
		if not cell.name then
			error('FootballQueries: every cell needs a name', 0)
		end
		local grain = cell.grain or 'event'
		if grain ~= 'event' and grain ~= 'game' then
			error(string.format(
				'FootballQueries: cell "%s" has unknown grain "%s" - it must say '
				.. 'whether it counts events or games', cell.name, grain), 0)
		end

		local cellBuilder = buildInto(cell.filters or {}, true)
		local condition = #cellBuilder.conditions > 0
			and table.concat(cellBuilder.conditions, ' AND ') or '1=1'

		-- Aliases are positional: a Hebrew cell name is not a safe SQL alias.
		local alias = 'c' .. index
		aliases[index] = { alias = alias, name = cell.name }

		if grain == 'game' then
			fields[index] = string.format(
				'COUNT(DISTINCT CASE WHEN %s THEN Football_Games._pageID END)=%s',
				condition, alias)
		else
			fields[index] = string.format(
				'SUM(CASE WHEN %s THEN 1 ELSE 0 END)=%s', condition, alias)
		end
	end

	local rows = runCargo(tables, table.concat(fields, ','), {
		join = join,
		where = whereOf(sharedBuilder),
		groupBy = options.groupBy,
		orderBy = options.orderBy,
		having = options.having,
		limit = options.limit or 2,
	})

	-- Without groupBy the answer is one row of cells; with it, one row per
	-- group, and the caller needs the group value alongside them.
	local function unpackRow(row)
		local values = {}
		for _, entry in ipairs(aliases) do
			-- Cargo returns SUM as a float and an empty group as nil.
			values[entry.name] = tonumber(row[entry.alias]) or 0
		end
		return values
	end

	if not options.groupBy then
		return rows[1] and unpackRow(rows[1]) or {}
	end

	local grouped = {}
	for index, row in ipairs(rows) do
		grouped[index] = { group = row[options.groupAlias or 'g'],
		                   cells = unpackRow(row) }
	end
	return grouped
end

--- Rows for one filter set. `options` is this module's own interface and is
--- therefore English: fields, groupBy, orderBy, having, limit.
function FootballQueries.query(filters, options)
	options = options or {}
	local query = FootballQueries.build(filters)

	return runCargo(query.tables, options.fields or 'COUNT(*)=n', {
		join = query.join,
		where = query.where,
		groupBy = options.groupBy,
		orderBy = options.orderBy,
		having = options.having,
		limit = options.limit,
	})
end

--- One number for one filter set, for the counts that make up a stats block.
--- Lua callers only: an `#invoke` reaches `count` below, which unpacks a frame.
function FootballQueries.countFilters(filters, aggregate)
	if type(filters) == 'table' and filters.getParent ~= nil then
		-- Handed a frame instead of a filter set. Without this the frame's own
		-- fields are read as filter names and the error blames a filter called
		-- "args", which sends the reader looking in the wrong place entirely.
		error('FootballQueries: countFilters takes a filter table, not a '
			.. 'frame - from wikitext use {{#invoke:FootballQueries|count|…}}',
			0)
	end
	local rows = FootballQueries.query(filters, {
		fields = (aggregate or 'COUNT(*)') .. '=n',
		limit = 2,
	})
	return tonumber(rows[1] and rows[1].n) or 0
end

--- #invoke entry point, so a count can be compared against the template it
--- replaces before any display module exists:
---   {{#invoke:FootballQueries|count|שחקן=ערן זהבי|קטגוריית מפעל=ליגה}}
function FootballQueries.count(frame)
	local filters = {}
	for name, value in pairs(frame.args) do
		if name ~= 'aggregate' then
			filters[name] = value
		end
	end

	-- `aggregate` lands in the field list, so it is SQL. Only the declared
	-- aggregates are allowed through; wikitext must never reach fields.
	local requested = frame.args.aggregate
	local aggregate = nil
	if requested and mw.text.trim(requested) ~= '' then
		aggregate = Fields.aggregates[mw.text.trim(requested)]
		if not aggregate then
			error(string.format(
				'FootballQueries: unknown aggregate "%s"', requested), 0)
		end
	end

	return FootballQueries.countFilters(filters, aggregate)
end

--- Splits template parameters into filters and query options, rejecting
--- anything that is neither.
local function separate(args)
	local filters, options = {}, {}
	for name, value in pairs(args) do
		local option = Fields.optionParams[name]
		if option then
			options[option] = value
		else
			filters[name] = value
		end
	end
	return filters, options
end

--- Proves the merge against real data from wikitext, before a display module
--- exists to consume it:
---   {{#invoke:FootballQueries|aggregateProbe|cells=goals:3,assists:4
---     |שחקן=ערן זהבי|קטגוריית מפעל=ליגה}}
---
--- `cells` is name:eventType pairs, comma separated. Diagnostic only - a real
--- block gets its cells from the block data page, not from wikitext.
function FootballQueries.aggregateProbe(frame)
	local shared = {}
	for name, value in pairs(frame.args) do
		if name ~= 'cells' then
			shared[name] = value
		end
	end

	local cells = {}
	for pair in tostring(frame.args.cells or ''):gmatch('[^,]+') do
		local name, eventType = pair:match('^%s*(%w+)%s*:%s*([%d;]+)%s*$')
		if not name then
			error(string.format(
				'FootballQueries: cells must be name:eventType pairs, got "%s"',
				pair), 0)
		end
		cells[#cells + 1] = {
			name = name,
			filters = { ['מספר אירוע'] = eventType:gsub(';', ',') },
		}
	end

	local values = FootballQueries.aggregate(shared, cells)
	local output = {}
	for _, cell in ipairs(cells) do
		output[#output + 1] = cell.name .. '=' .. tostring(values[cell.name])
	end
	return table.concat(output, ' ')
end

--- Drop-in body for a query template, replacing its whole #cargo_query:
---   {{#invoke:FootballQueries|gameDataCount}}
---
--- It reads the *parent* frame, so the template forwards nothing by name and
--- therefore cannot drop anything. A shim that forwards a fixed parameter list
--- silently defeats the unsupported-filter guard - that bug shipped once, and
--- an opponent page asking for its own yellow cards was handed the wiki-wide
--- total. Enumerating no parameters is the only way the guard stays honest.
function FootballQueries.gameDataCount(frame)
	-- This entry point deliberately reads the PARENT frame, so arguments given
	-- to the #invoke itself would be ignored - and an ignored filter returns
	-- the wiki-wide total, which is the failure this module exists to prevent.
	-- Measured on the local wiki: called directly with עונה=2021/22 it returned
	-- 222, every game, instead of 59.
	-- `next` does not work on frame.args: Scribunto populates it lazily behind
	-- a metatable, so next() reports empty however many parameters were given.
	-- Measured: the guard below never fired until it was written with pairs.
	local hasDirectArgs = false
	for _ in pairs(frame.args) do
		hasDirectArgs = true
		break
	end

	if hasDirectArgs then
		error('FootballQueries: gameDataCount reads the calling template\'s '
			.. 'parameters, so it takes none of its own. Put it in a template '
			.. 'body as {{#invoke:FootballQueries|gameDataCount}}, or use '
			.. '{{#invoke:FootballQueries|count|…}} to pass filters directly.',
			0)
	end

	local filters, options = separate(frame:getParent().args)

	local requested = options.aggregate and mw.text.trim(options.aggregate) or ''
	local aggregate = 'COUNT(*)'
	if requested ~= '' then
		aggregate = Fields.aggregates[requested]
		if not aggregate then
			error(string.format(
				'FootballQueries: unknown נתון משחק "%s"', requested), 0)
		end
	end

	local value = FootballQueries.countFilters(filters, aggregate)
	-- The template rounds SUM's float back to an integer with #number_format
	-- and then strips the thousands separators again; the result is a bare
	-- integer, rounded half-up.
	return string.format('%d', math.floor(value + 0.5))
end

return FootballQueries
