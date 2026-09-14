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
	local tables = {}
	tables[Fields.baseTable] = true
	return setmetatable({ conditions = {}, tables = tables }, Builder)
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
	-- Both values come from the schema: they are 1 and 0 in football and the
	-- opponent is 2 in volleyball.
	local side = normalise(value) == Fields.sides.opponentValue
		and Fields.sides.opponent or Fields.sides.maccabi
	builder:addComparison(spec.column, '=', side)
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
--- `modifiers` is where handlers look up parameters that modify another
--- filter rather than producing a condition - פורמט תאריך for תאריך. It
--- defaults to `filters`, and the merge passes the union, because the modifier
--- can sit in the shared filters while the filter it modifies sits in a cell.
local function buildInto(filters, skipDefaults, modifiers)
	local builder = newBuilder()
	modifiers = modifiers or filters

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
			handlers[spec.kind](builder, spec, value, modifiers)
		end
	end

	-- Every query template that touches Games_Events constrains Team: most
	-- hardcode `AND Team = 1`, the rest default the מכבי parameter to it. So an
	-- events query without it is not "unfiltered", it is wrong - it counts the
	-- opponent's events too. Measured: a league goals count for one player
	-- returns 152 without this and 150 with it, because two rows on that page
	-- belong to the opposing side.
	if builder.tables[Fields.roles.events] and not builder.teamConstrained
			and not skipDefaults then
		builder:addComparison(Fields.roles.sideColumn, '=', Fields.sides.maccabi)
	end

	return builder
end

--- Turns a builder's tables into the tables and join of a query.
local function tablesAndJoin(builder)
	local joined = {}
	for name in pairs(builder.tables) do
		if name ~= Fields.baseTable then
			joined[#joined + 1] = name
		end
	end
	table.sort(joined)

	-- Only the tables the filters actually reached. Cargo's join on is a LEFT
	-- JOIN, so omitting an unused table cannot change a row count.
	local tableNames = { Fields.baseTable }
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

	-- The WHERE carries the shared filters only, and deliberately NOT the Team
	-- default. Putting Team in the WHERE of a merged query is wrong twice over,
	-- both measured:
	--
	--  * a cell asking for the opponent's side (מכבי=לא) can never match, since
	--    the WHERE already demands Team = 1 and the cell's CASE demands 0 - a
	--    contradiction that returns 0 with no error;
	--  * `Games_Events.Team = 1` in the WHERE discards the NULL row a LEFT JOIN
	--    produces for a game with no events, which turns the join back into an
	--    inner one. A game-grain cell then undercounts: 3,439 games instead of
	--    3,504 on production, 65 lost.
	--
	-- So the default goes into each event cell's own CASE instead, where it
	-- constrains the events being counted without touching the row set.
	local sharedBuilder = buildInto(shared, true)
	local teamDefaultNeeded = unionBuilder.tables[Fields.roles.events]
		and not sharedBuilder.teamConstrained

	local fields = {}
	local aliases = {}
	local seen = {}
	for index, cell in ipairs(cells) do
		if not cell.name then
			error('FootballQueries: every cell needs a name', 0)
		end
		if seen[cell.name] then
			-- Two cells of the same name silently collapse into whichever came
			-- last, which is a missing number rather than an error.
			error(string.format(
				'FootballQueries: two cells are both named "%s"', cell.name), 0)
		end
		seen[cell.name] = true

		local grain = cell.grain
		if grain ~= 'event' and grain ~= 'game' then
			-- Not defaulted: an event-grain guess for a cell that counts games
			-- multiplies it by the number of events on the page, up to 43x.
			error(string.format(
				'FootballQueries: cell "%s" must declare grain as "event" or '
				.. '"game", got %s', cell.name, tostring(grain)), 0)
		end

		-- Modifier parameters such as פורמט תאריך may live in the shared
		-- filters while the filter they modify lives in a cell, so a cell's
		-- handlers look modifiers up in the shared filters plus its OWN - not
		-- in the union. The union let a later cell's פורמט תאריך overwrite an
		-- earlier cell's: two cells asking for different date formats both
		-- rendered the last one, so one of them silently answered a different
		-- question.
		local modifiers = {}
		for name, value in pairs(shared) do
			modifiers[name] = value
		end
		for name, value in pairs(cell.filters or {}) do
			modifiers[name] = value
		end

		local cellBuilder = buildInto(cell.filters or {}, true, modifiers)
		local conditions = {}
		for _, condition in ipairs(cellBuilder.conditions) do
			conditions[#conditions + 1] = condition
		end

		-- The side constraint belongs to any cell whose conditions reach the
		-- events table, whatever its grain. Restricting it to event grain left
		-- a game-grain cell counting games in which EITHER side did the thing:
		-- `{grain='game', filters={מספר אירוע=3}}` emitted
		-- COUNT(DISTINCT CASE WHEN EventType IN (3) THEN _pageID END), and the
		-- opponent-side rows that make that wrong are the same ones behind the
		-- 152-versus-150 measurement. A game-grain cell with no event filters
		-- still gets nothing, which is correct - it counts games, not events.
		if teamDefaultNeeded and not cellBuilder.teamConstrained
				and cellBuilder.tables[Fields.roles.events] then
			conditions[#conditions + 1] = string.format('%s = %s',
				Fields.roles.sideColumn, Fields.sides.maccabi)
		end

		local condition = #conditions > 0
			and table.concat(conditions, ' AND ') or '1=1'

		if condition:find(' HOLDS ', 1, true) then
			-- Cargo rewrites HOLDS only in the where clause, so one in a field
			-- reaches MySQL verbatim and fails there.
			error(string.format(
				'FootballQueries: cell "%s" uses a HOLDS filter, which Cargo only '
				.. 'rewrites in the where - pass it as a shared filter instead',
				cell.name), 0)
		end

		-- Aliases are positional: a Hebrew cell name is not a safe SQL alias.
		local alias = 'c' .. index
		aliases[index] = { alias = alias, name = cell.name,
		                   sums = cell.sum ~= nil }

		if cell.sum then
			-- A cell that sums a column of the base table rather than counting
			-- rows: goals for, goals against. Joining the events table would
			-- repeat each game once per event and multiply the sum, so that is
			-- refused rather than quietly returned.
			local column = Fields.sumColumns[cell.sum]
			if not column then
				error(string.format(
					'FootballQueries: cell "%s" sums "%s", which is not a known '
					.. 'summable value', cell.name, tostring(cell.sum)), 0)
			end
			if grain ~= 'game' then
				error(string.format(
					'FootballQueries: cell "%s" sums a game column, so its grain '
					.. 'must be "game"', cell.name), 0)
			end
			if unionBuilder.tables[Fields.roles.events] then
				error(string.format(
					'FootballQueries: cell "%s" sums a game column while the '
					.. 'query joins %s, which would multiply it by the number '
					.. 'of events', cell.name, Fields.roles.events), 0)
			end
			-- ELSE NULL, not ELSE 0. SUM skips NULLs and is NULL when every
			-- row is skipped, which is exactly what the template's own
			-- SUM(column) returns when nothing matches - and the templates
			-- render that as an empty cell. With ELSE 0 the sum is 0 as soon
			-- as the query matches ANY row, so a cup tab on a date with only
			-- league games printed "0" where the template prints nothing.
			-- Measured: over 222 rows, ELSE 0 gives 0 and ELSE NULL gives NULL.
			fields[index] = string.format(
				'SUM(CASE WHEN %s THEN %s ELSE NULL END)=%s',
				condition, column, alias)
		elseif grain == 'game' then
			fields[index] = string.format(
				'COUNT(DISTINCT CASE WHEN %s THEN %s._pageID END)=%s',
				condition, Fields.baseTable, alias)
		else
			fields[index] = string.format(
				'SUM(CASE WHEN %s THEN 1 ELSE 0 END)=%s', condition, alias)
		end
	end

	-- Ungrouped on purpose. A leaderboard needs GROUP BY, ordering, a limit and
	-- HAVING, and it needs the group column in the SELECT - a different
	-- primitive, not an option on this one. An earlier version accepted
	-- `groupBy` here and could not work: it never selected the group column, so
	-- every group came back nil, and its test passed only because the stub
	-- fabricated the column. It gets written when the leaderboards are.
	-- Removing the grouped branch left orderBy, having and groupAlias accepted
	-- and unread, which is the silent-ignore this module exists to refuse.
	for name in pairs(options) do
		if name ~= 'limit' then
			error(string.format(
				'FootballQueries: aggregate does not take "%s" - it answers one '
				.. 'row of cells, and grouping, ordering and having belong to '
				.. 'the leaderboard primitive, which is a separate function',
				name), 0)
		end
	end

	local rows = runCargo(tables, table.concat(fields, ','), {
		join = join,
		where = whereOf(sharedBuilder),
		limit = options.limit or 2,
	})

	local values = {}
	if rows[1] then
		for _, entry in ipairs(aliases) do
			-- COUNT over no rows is 0; SUM over no rows is NULL, and the
			-- templates render that as an empty cell rather than a zero. The
			-- difference is visible on a date with no games, so a summing cell
			-- keeps nil and a counting cell does not.
			local value = tonumber(rows[1][entry.alias])
			if value == nil and not entry.sums then
				value = 0
			end
			values[entry.name] = value
		end
	end
	return values
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
	-- nil, not 0, when the database answered NULL. An aggregate query always
	-- returns a row, so the only way to get here without a number is a SUM
	-- over nothing - and the templates print an empty cell for that, not a
	-- zero. COUNT is unaffected: it is 0 over no rows, and 0 is a number.
	return tonumber(rows[1] and rows[1].n)
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

	-- Same rule as the shim: NULL is an empty cell, never a zero.
	local value = FootballQueries.countFilters(filters, aggregate)
	if value == nil then
		return ''
	end
	return value
end

--- Splits template parameters into filters and query options, rejecting
--- anything that is neither.
---
--- `entryPoint` names a declaration in Fields.entryPoints. When given, only
--- the parameters that entry point declares are accepted: a replacement for a
--- template must not answer questions that template could not be asked, or it
--- answers a different question and looks right doing it.
local function separate(args, entryPoint)
	local allowedFilters, allowedOptions
	if entryPoint then
		local declaration = Fields.entryPoints[entryPoint]
		if not declaration then
			error(string.format(
				'FootballQueries: no entry point declared as "%s"', entryPoint), 0)
		end
		allowedFilters, allowedOptions = {}, {}
		for _, name in ipairs(declaration.filters) do
			allowedFilters[name] = true
		end
		for _, name in ipairs(declaration.options) do
			allowedOptions[name] = true
		end
	end

	local filters, options = {}, {}
	for name, value in pairs(args) do
		local option = Fields.optionParams[name]
		if option then
			if allowedOptions and not allowedOptions[name] then
				error(string.format(
					'FootballQueries: %s does not take "%s" - the template it '
					.. 'replaces has no such parameter', entryPoint, name), 0)
			end
			options[option] = value
		else
			if allowedFilters and not allowedFilters[name]
					and mw.text.trim(tostring(value)) ~= '' then
				error(string.format(
					'FootballQueries: %s does not take the filter "%s" - the '
					.. 'template it replaces has no such parameter, and '
					.. 'answering it would answer a different question',
					entryPoint, name), 0)
			end
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
--- The parameters a shim was invoked with, refusing any given to the #invoke
--- itself. Shared by the shims because reading the wrong frame is the same
--- silent failure in each: an ignored filter returns the wiki-wide total.
local function parentArgumentsOf(frame, entryPoint)
	-- `next` does not work on frame.args: Scribunto populates it lazily behind
	-- a metatable, so next() reports empty however many parameters were given.
	-- Measured: the guard below never fired until it was written with pairs.
	for _ in pairs(frame.args) do
		error(string.format(
			'FootballQueries: %s reads the calling template\'s parameters, so '
			.. 'it takes none of its own. Put it in a template body as '
			.. '{{#invoke:FootballQueries|%s}}, or use '
			.. '{{#invoke:FootballQueries|count|…}} to pass filters directly.',
			entryPoint, entryPoint), 0)
	end

	return separate(frame:getParent().args, entryPoint)
end

--- Drop-in body for תבנית:סטטיסטיקה/שליפות/מתקדמות/כמות אירועי שחקן, the
--- other query template the display blocks call:
---   {{#invoke:FootballQueries|playerEventCount}}
---
--- It counts events, never games, and its parameter list is its own: asking it
--- for נתון משחק would answer a question the template it replaces cannot be
--- asked. Same frame rule as gameDataCount below.
function FootballQueries.playerEventCount(frame)
	local filters = parentArgumentsOf(frame, 'playerEventCount')
	return string.format(
		'%d', math.floor(FootballQueries.countFilters(filters) + 0.5))
end

function FootballQueries.gameDataCount(frame)
	-- This entry point deliberately reads the PARENT frame, so arguments given
	-- to the #invoke itself would be ignored - and an ignored filter returns
	-- the wiki-wide total, which is the failure this module exists to prevent.
	-- Measured on the local wiki: called directly with עונה=2021/22 it returned
	-- 222, every game, instead of 59.
	local filters, options = parentArgumentsOf(frame, 'gameDataCount')

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
	-- A SUM over nothing is NULL, and the template prints an empty cell for
	-- it: {{#number_format:}} of nothing is nothing. Printing 0 here would
	-- disagree on every day page with no games in one of its four categories.
	if value == nil then
		return ''
	end

	-- The template rounds SUM's float back to an integer with #number_format
	-- and then strips the thousands separators again; the result is a bare
	-- integer, rounded half-up.
	return string.format('%d', math.floor(value + 0.5))
end

return FootballQueries
