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
	['&quot;'] = '"',
	['&#39;'] = "'",
	['&apos;'] = "'",
}

local function normalise(value)
	value = tostring(value)
	for entity, character in pairs(ENTITIES) do
		value = value:gsub(entity, character)
	end
	return mw.text.trim(value)
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
	elseif value:find('"', 1, true) then
		-- Values here keep apostrophes, which are safe inside double quotes; a
		-- double quote would end the literal and is rejected rather than mangled.
		error(string.format(
			'FootballQueries: %s value contains a double quote: %s', column, value), 0)
	end

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
			.. literalByRule(spec.quotes, spec.matchColumn, value),
		limit = Fields.defaultLimit,
	})

	local names = {}
	for index, row in ipairs(rows) do
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

--- Turns a filter set into the tables, join and where of one query.
function FootballQueries.build(filters)
	local builder = newBuilder()

	-- Sorted, so the same filter set always produces byte-identical SQL: it
	-- keeps the generated query diffable and comparable between runs.
	local names = {}
	for name in pairs(filters) do
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

	return {
		tables = table.concat(tableNames, ','),
		join = table.concat(joins, ','),
		where = #builder.conditions > 0
			and table.concat(builder.conditions, ' AND ') or '1=1',
	}
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
function FootballQueries.count(filters, aggregate)
	local rows = FootballQueries.query(filters, {
		fields = (aggregate or 'COUNT(*)') .. '=n',
		limit = 2,
	})
	return tonumber(rows[1] and rows[1].n) or 0
end

--- #invoke entry point, so a count can be compared against the template it
--- replaces before any display module exists:
---   {{#invoke:FootballQueries|count|שחקן=ערן זהבי|קטגוריית מפעל=ליגה}}
function FootballQueries.countFromFrame(frame)
	local filters = {}
	for name, value in pairs(frame.args) do
		if name ~= 'aggregate' then
			filters[name] = value
		end
	end
	return FootballQueries.count(filters, frame.args.aggregate)
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

--- Drop-in body for a query template, replacing its whole #cargo_query:
---   {{#invoke:FootballQueries|gameDataCount}}
---
--- It reads the *parent* frame, so the template forwards nothing by name and
--- therefore cannot drop anything. A shim that forwards a fixed parameter list
--- silently defeats the unsupported-filter guard - that bug shipped once, and
--- an opponent page asking for its own yellow cards was handed the wiki-wide
--- total. Enumerating no parameters is the only way the guard stays honest.
function FootballQueries.gameDataCount(frame)
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

	local value = FootballQueries.count(filters, aggregate)
	-- The template rounds SUM's float back to an integer with #number_format
	-- and then strips the thousands separators again; the result is a bare
	-- integer, rounded half-up.
	return string.format('%d', math.floor(value + 0.5))
end

return FootballQueries
