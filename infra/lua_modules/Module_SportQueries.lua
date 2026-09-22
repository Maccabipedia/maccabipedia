--[[
Module:SportQueries - one Cargo query from one filter set, for any sport.

Wiki page: Module:SportQueries

The logic of Module:FootballQueries with the schema handed in instead of loaded
here, so one code page serves every sport: a sport is a schema page
(tables, columns, quote rules, filters, competition categories, result words,
sides, aggregates, entry points) and a five-line module that binds it -

    return require('Module:SportQueries').new(mw.loadData('Module:FootballQueries/Fields'))

`new` builds a fresh table of entry points around the schema it was given and
keeps no module-level state, so a page may bind two sports without one
overwriting the other. Error messages carry the schema's `name`, which is why
football's read exactly as they did.

Nothing else changed: the body below is Module:FootballQueries as it was, with
`FootballQueries` renamed `Queries` and indented one tab. Compare with
`diff -w` against that file's last standalone revision.
]]

local SportQueries = {}

function SportQueries.new(Fields)

	local Queries = {}
	local NAME = Fields.name

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
	--- SQL. Proven read-only against production: a value built as an encoded
	--- quote, then a disjunction that is always true, then another encoded quote,
	--- returned every row in the table instead of raising - the wiki-wide-total
	--- bug, reappearing inside the module written to prevent it.
	---
	--- That probe is DESCRIBED rather than quoted on purpose. Written out
	--- literally, the six characters of the always-true disjunction are refused
	--- by the wiki's web application firewall in any POST body, so the module
	--- could not be saved at all: pywikibot reads the rejection as a non-JSON
	--- response and retries it forever, two minutes apart, which looks like the
	--- wiki hanging rather than like a blocked edit. Measured against production:
	--- those six bytes alone are rejected, while 64KB of harmless text is not.
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
				NAME .. ': value contains an ampersand, which Cargo would '
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
				NAME .. ': no quote rule declared for column %s', column), 0)
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
					NAME .. ': %s expects a number, got "%s"', column, value), 0)
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
				NAME .. ': column %s belongs to no known table', column), 0)
		end
		return tableName
	end

	--- What one row of a table stands for, declared per table in the schema:
	--- 'game' (at most one row per base row - the game itself, its competition,
	--- its referees) or 'perPlayer' (several rows per game - football's events,
	--- basketball's per-player summaries). Joining a 'perPlayer' table multiplies
	--- the base rows, which is what every grain rule below is about.
	local function grainOf(tableName)
		local declaration = Fields.tables[tableName]
		local grain = declaration and declaration.grain
		if grain ~= 'game' and grain ~= 'perPlayer' then
			error(string.format(
				NAME .. ': table %s declares no grain ("game" or "perPlayer")',
				tableName), 0)
		end
		return grain
	end

	--- The one multiplying table a query joins, or nil. Two would multiply each
	--- other and no cell grain can undo that, so two is an error.
	local function multiplyingJoined(tables)
		local names = {}
		for name in pairs(tables) do
			if grainOf(name) == 'perPlayer' then
				names[#names + 1] = name
			end
		end
		table.sort(names)
		if #names > 1 then
			error(string.format(
				NAME .. ': the query joins two multiplying tables, %s and %s, '
				.. 'which would multiply each other', names[1], names[2]), 0)
		end
		return names[1]
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
				NAME .. ': no values to match for %s', column), 0)
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
					NAME .. ': הגבלה must be a number, got "%s"',
					tostring(options.limit)), 0)
			end
			options.limit = math.floor(limit)
		end
		options.limit = options.limit or Fields.defaultLimit
		if options.limit > Fields.maxLimit then
			error(string.format(
				NAME .. ': limit %d exceeds maxLimit %d',
				options.limit, Fields.maxLimit), 0)
		end

		local rows = mw.ext.cargo.query(tables, fields, options)

		if #rows >= options.limit then
			-- Cargo truncates silently. A block built from a cut-off result is a
			-- normal-looking table of wrong numbers, so this is fatal.
			error(string.format(
				NAME .. ': query returned %d rows and hit the limit of %d - '
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
			--
			-- A stored name carrying an ampersand is refused here rather than
			-- further down, where the message would blame the caller's value.
			-- Production has 11 such rows in Stadiums.CanonicalName - double
			-- encoded, e.g. אצטדיון ימק&amp;#34;א - and the entity guard in
			-- normalise() would fire on them with no hint that the fault is in the
			-- wiki's data rather than in the query. Football_Games.Stadium itself
			-- holds none, so no game is reachable through such a name anyway.
			if tostring(row.name):find('&', 1, true) then
				error(string.format(
					NAME .. ': the %s table stores "%s" with an HTML entity '
					.. 'in it, so it cannot be matched - fix that row on the wiki',
					kind, tostring(row.name)), 0)
			end
			names[index] = row.name
		end
		if #names == 0 then
			error(string.format(
				NAME .. ': %s "%s" matched no known name', kind, value), 0)
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
		local items = splitList(value)
		if spec.stripPrefix then
			-- A list the page built from category members carries the namespace
			-- (basketball's "כדורסל:Name"), which the stored name lacks. Left on, IN
			-- matches nothing and every box renders empty with no error.
			for index, item in ipairs(items) do
				if item:sub(1, #spec.stripPrefix) == spec.stripPrefix then
					items[index] = item:sub(#spec.stripPrefix + 1)
				end
			end
		end
		builder:addIn(spec.column, items)
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

	--- A word the templates accept, mapped by the schema to a ready SQL
	--- condition: קטגוריית מפעל (ליגה → Competitions.League = 1), תוצאה
	--- (ניצחון → Football_Games.ResultOpt = 1). The spec names the tables the
	--- conditions reach, and a choice may map to '' - a word that means "no
	--- condition" (basketball's רשמי tab does). An unknown word is an error.
	handlers.choice = function(builder, spec, value, _, name)
		local condition = spec.choices[normalise(value)]
		if condition == nil then
			error(string.format(
				NAME .. ': unknown %s "%s"', name, value), 0)
		end
		for _, tableName in ipairs(spec.tables or {}) do
			builder.tables[tableName] = true
		end
		if condition ~= '' then
			builder:add(condition)
		end
	end
	-- The two choices every sport has, under the kind names the schemas use.
	handlers.competitionCategory = handlers.choice
	handlers.resultWord = handlers.choice

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
				NAME .. ': unsafe פורמט תאריך "%s"', format), 0)
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
					NAME .. ': positional parameter %s - every filter must be '
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
					NAME .. ': unsupported filter "%s"', name), 0)
			end
			-- Templates pass every parameter whether or not it was set, so an empty
			-- value means "not provided" rather than "match the empty string".
			if value ~= nil and mw.text.trim(tostring(value)) ~= '' then
				handlers[spec.kind](builder, spec, value, modifiers, name)
			end
		end

		-- Every query template that touches Games_Events constrains Team: most
		-- hardcode `AND Team = 1`, the rest default the מכבי parameter to it. So an
		-- events query without it is not "unfiltered", it is wrong - it counts the
		-- opponent's events too. Measured: a league goals count for one player
		-- returns 152 without this and 150 with it, because two rows on that page
		-- belong to the opposing side. The same holds for any sport's multiplying
		-- table: its rows carry a side.
		if multiplyingJoined(builder.tables) and not builder.teamConstrained
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
	function Queries.build(filters)
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
	--- Compiles cells into one SELECT's fields over one WHERE: the part `aggregate`
	--- and `leaderboard` share. Every rule below applies to both - the Team default
	--- inside each cell, HOLDS only in the WHERE, the sum guards - so the two
	--- primitives cannot drift apart on what a cell means.
	local function compileCells(shared, cells)
		if #cells == 0 then
			error(NAME .. ': aggregate needs at least one cell', 0)
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
		-- A summed column's table is part of the query even when no filter
		-- reaches it (basketball's points live on the per-player table; the
		-- filters may all be about the game).
		local sumColumnOf = {}
		for _, cell in ipairs(cells) do
			if cell.sum then
				local column = Fields.sumColumns[cell.sum]
				if not column then
					error(string.format(
						NAME .. ': cell "%s" sums "%s", which is not a known '
						.. 'summable value', tostring(cell.name), tostring(cell.sum)), 0)
				end
				sumColumnOf[cell] = column
				unionBuilder:needs(column)
			end
		end
		local tables, join = tablesAndJoin(unionBuilder)
		local multiplying = multiplyingJoined(unionBuilder.tables)

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
		local teamDefaultNeeded = multiplying ~= nil
			and not sharedBuilder.teamConstrained

		local fields = {}
		local aliases = {}
		local seen = {}
		for index, cell in ipairs(cells) do
			if not cell.name then
				error(NAME .. ': every cell needs a name', 0)
			end
			if seen[cell.name] then
				-- Two cells of the same name silently collapse into whichever came
				-- last, which is a missing number rather than an error.
				error(string.format(
					NAME .. ': two cells are both named "%s"', cell.name), 0)
			end
			seen[cell.name] = true

			local grain = cell.grain
			if grain ~= 'event' and grain ~= 'game' then
				-- Not defaulted: an event-grain guess for a cell that counts games
				-- multiplies it by the number of events on the page, up to 43x.
				error(string.format(
					NAME .. ': cell "%s" must declare grain as "event" or '
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
			if sumColumnOf[cell] then
				-- The summed column is something the cell reaches, so a sum over
				-- the multiplying table gets the side constraint below like any
				-- other cell that touches it.
				cellBuilder:needs(sumColumnOf[cell])
			end
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
					and cellBuilder.tables[multiplying] then
				conditions[#conditions + 1] = string.format('%s = %s',
					Fields.roles.sideColumn, Fields.sides.maccabi)
			end

			local condition = #conditions > 0
				and table.concat(conditions, ' AND ') or '1=1'

			if condition:find(' HOLDS ', 1, true) then
				-- Cargo rewrites HOLDS only in the where clause, so one in a field
				-- reaches MySQL verbatim and fails there.
				error(string.format(
					NAME .. ': cell "%s" uses a HOLDS filter, which Cargo only '
					.. 'rewrites in the where - pass it as a shared filter instead',
					cell.name), 0)
			end

			-- Aliases are positional: a Hebrew cell name is not a safe SQL alias.
			local alias = 'c' .. index
			aliases[index] = { alias = alias, name = cell.name,
			                   sums = cell.sum ~= nil, condition = condition }

			if cell.sum then
				-- A cell that sums a column rather than counting rows. Its grain
				-- is the grain of the column's TABLE, declared in the schema, and
				-- the cell must say the same - a guess here multiplies numbers.
				--   'game' column (goals for, goals against): the query must not
				--   join a multiplying table, or each game repeats once per event
				--   and the sum with it - refused rather than quietly returned.
				--   'perPlayer' column (basketball's points): the cell is one row
				--   per player per game, i.e. event grain, and its table is joined
				--   above whether or not a filter reached it.
				local column = sumColumnOf[cell]
				local columnGrain = grainOf(tableOf(column))
				if columnGrain == 'game' and grain ~= 'game' then
					error(string.format(
						NAME .. ': cell "%s" sums a game column, so its grain '
						.. 'must be "game"', cell.name), 0)
				end
				if columnGrain == 'game' and multiplying then
					error(string.format(
						NAME .. ': cell "%s" sums a game column while the '
						.. 'query joins %s, which would multiply it by the number '
						.. 'of events', cell.name, multiplying), 0)
				end
				if columnGrain == 'perPlayer' and grain ~= 'event' then
					error(string.format(
						NAME .. ': cell "%s" sums a per-player column, so its '
						.. 'grain must be "event"', cell.name), 0)
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
				if not multiplying then
					-- Counting rows of a query that joins no multiplying table is
					-- counting games, and a cell that says "event" while doing that
					-- is a game count wearing the wrong label.
					error(string.format(
						NAME .. ': cell "%s" counts events, but the query joins no '
						.. 'multiplying table - declare grain "game"', cell.name), 0)
				end
				fields[index] = string.format(
					'SUM(CASE WHEN %s THEN 1 ELSE 0 END)=%s', condition, alias)
			end
		end

		return {
			tables = tables,
			join = join,
			where = whereOf(sharedBuilder),
			fields = fields,
			aliases = aliases,
		}
	end

	function Queries.aggregate(shared, cells, options)
		options = options or {}
		local compiled = compileCells(shared, cells)

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
					NAME .. ': aggregate does not take "%s" - it answers one '
					.. 'row of cells, and grouping, ordering and having belong to '
					.. 'the leaderboard primitive, which is a separate function',
					name), 0)
			end
		end

		local rows = runCargo(compiled.tables, table.concat(compiled.fields, ','), {
			join = compiled.join,
			where = compiled.where,
			limit = options.limit or 2,
		})

		local values = {}
		-- An aggregate with no GROUP BY always returns exactly one row - that is
		-- SQL, not a Cargo detail - so no rows at all means the query did not run
		-- as asked rather than that nothing matched. Left alone, every cell would
		-- be nil and the renderer would raise "the block has no cell named wins",
		-- which is untrue and sends the reader to the wrong file.
		if not rows[1] then
			error(NAME .. ': the merged query returned no rows at all. An '
				.. 'aggregate always returns one row, so this is a failed query, '
				.. 'not an empty result', 0)
		end
		for _, entry in ipairs(compiled.aliases) do
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
		return values
	end

	-- Defined below `leaderboard`, which reads more naturally top-down; declared
	-- here so it is a local rather than a global.
	local narrowShared

	--- Ranks one column's counts: non-zero only, count DESC then name ASC, top N.
	---
	--- The name tiebreak is a deliberate departure. The templates order by the
	--- count alone, so tied players come back in whatever order MySQL returns and
	--- the last row of a top ten can change between two renders of the same page.
	---
	--- Lua compares bytes; the "עוד" page's ORDER BY uses MySQL's collation. For
	--- Hebrew names both follow the letter order, but for mixed-case Latin names
	--- or trailing spaces the two can differ, so a player tied exactly at rank ten
	--- could show in the box and again on the "עוד" page, or on neither. Accepted:
	--- it needs such a name inside a tie at the cutoff.
	local function rank(entries, top, keepZero)
		local ranked = {}
		for _, entry in ipairs(entries) do
			-- Football's templates had HAVING > 0; basketball's show a zero
			-- (COALESCE), so a block may ask to keep them.
			if entry.count > 0 or keepZero then
				ranked[#ranked + 1] = entry
			end
		end
		table.sort(ranked, function(left, right)
			if left.count ~= right.count then
				return left.count > right.count
			end
			return left.name < right.name
		end)

		local shown = {}
		for index = 1, math.min(top, #ranked) do
			shown[index] = ranked[index]
		end
		return {
			rows = shown,
			players = #ranked,
			-- MORE than `top`, where Cargo's own link appears at EQUAL to the
			-- limit and so sends a tab of exactly ten players to an empty page.
			more = #ranked > top,
		}
	end

	--- The column a leaderboard's group key names, for callers that build a link
	--- to the same ranking (the "עוד" page). Raises for an unknown key.
	function Queries.groupKeyColumn(groupBy)
		local key = Fields.groupKeys[groupBy or '']
		if not key then
			error(string.format(
				NAME .. ': leaderboard needs groupBy naming a group key, '
				.. 'got "%s"', tostring(groupBy)), 0)
		end
		return key
	end

	--- Any number of leaderboards that share one WHERE, from ONE grouped query.
	---
	---   Queries.leaderboard(
	---     { ['עוזר שופט'] = 'דודו ביטון', ['קטגוריית מפעל'] = 'רשמי' },
	---     { { name = 'league-apps', grain = 'event',
	---         filters = { ['מספר אירוע'] = '1,5', ['קטגוריית מפעל'] = 'ליגה' } } },
	---     { groupBy = 'player', top = 10 })
	---
	--- Returns, per column name: rows = {{name, count}} (top N), players = how
	--- many had a non-zero count, more = whether there are more than N.
	---
	--- The template runs one grouped query per leaderboard plus one more per tab
	--- just to count its rows. Here every column is a conditional count over the
	--- same groups, so the ordering, the top N and the distinct count all come from
	--- one result - four boxes of four tabs is 32 queries in the template, one here.
	function Queries.leaderboard(shared, columns, options)
		options = options or {}
		for name in pairs(options) do
			if name ~= 'groupBy' and name ~= 'top' and name ~= 'keepZero' then
				error(string.format(
					NAME .. ': leaderboard does not take "%s"', name), 0)
			end
		end
		local key = Queries.groupKeyColumn(options.groupBy)
		local top = tonumber(options.top or 10)
		if not top or top < 1 or top ~= math.floor(top) then
			error(string.format(
				NAME .. ': leaderboard top must be a positive whole number, '
				.. 'got "%s"', tostring(options.top)), 0)
		end
		if #columns == 0 then
			error(NAME .. ': leaderboard needs at least one column', 0)
		end

		local compiled = compileCells(narrowShared(shared, columns), columns)
		local keyTable = key:match('^([^.]+)%.')
		if not (',' .. compiled.tables .. ','):find(',' .. keyTable .. ',', 1, true) then
			error(string.format(
				NAME .. ': leaderboard groups by %s, but no column reaches '
				.. '%s', key, keyTable), 0)
		end

		local rows = runCargo(compiled.tables,
			key .. '=g,' .. table.concat(compiled.fields, ','), {
				join = compiled.join,
				where = compiled.where,
				groupBy = key,
				-- Every group, so the top N and the distinct count are exact; the
				-- limit guard in runCargo raises instead of ranking a cut-off list.
				limit = Fields.maxLimit,
			})

		local result = {}
		for _, entry in ipairs(compiled.aliases) do
			local entries = {}
			for _, row in ipairs(rows) do
				entries[#entries + 1] = {
					-- A blank name is kept as a blank row, as the template shows
					-- one (none exist on production: 0 events, measured).
					name = row.g or '',
					count = tonumber(row[entry.alias]) or 0,
				}
			end
			result[entry.name] = rank(entries, top, options.keepZero)
		end
		return result
	end

	--- ONE column of a leaderboard as a standalone query - the shared WHERE plus
	--- that column's own condition - for a link to the same ranking (the "עוד"
	--- page). Compiled by the same code as the merged query, so a link cannot
	--- count something its box does not: rebuilding it from a filter set lost
	--- Competitions.Official = 1 on the league tab, because the tab's category
	--- and the shared רשמי are the same filter name.
	function Queries.leaderboardColumnQuery(shared, columns, name)
		for _, column in ipairs(columns) do
			if column.name == name then
				-- The column alone, so the WHERE narrows to ITS event types rather
				-- than the whole widget's union - the link states its own query.
				local compiled = compileCells(narrowShared(shared, { column }), { column })
				return {
					tables = compiled.tables,
					join = compiled.join,
					where = compiled.where .. ' AND ' .. compiled.aliases[1].condition,
				}
			end
		end
		error(string.format(
			NAME .. ': the leaderboard has no column named "%s"', name), 0)
	end

	--- The shared filters of a leaderboard, narrowed. Used by the query and by the
	--- per-column link query alike, so both carry the same WHERE.
	narrowShared = function(shared, columns)
		-- Every column counts some event types. Their union goes into the WHERE so
		-- rows outside all of them are never grouped; it cannot change a column's
		-- count, because each column still applies its own types in its CASE.
		local narrowed = {}
		for name, value in pairs(shared) do
			narrowed[name] = value
		end
		local narrowFilter = Fields.roles.narrowFilter
		if narrowFilter and narrowed[narrowFilter] == nil then
			local types, seen, everyColumn = {}, {}, true
			for _, column in ipairs(columns) do
				local value = column.filters and column.filters[narrowFilter]
				if not value or mw.text.trim(tostring(value)) == '' then
					everyColumn = false
					break
				end
				for _, item in ipairs(splitList(value)) do
					if not seen[item] then
						seen[item] = true
						types[#types + 1] = item
					end
				end
			end
			if everyColumn then
				narrowed[narrowFilter] = table.concat(types, ',')
			end
		end

		-- Maccabi's side into the WHERE when no column asks for a side. Every
		-- column would apply Team = 1 in its own CASE anyway, so the counts are
		-- unchanged; what changes is that the opponent players - over half the
		-- groups, 345 for one referee locally - are never grouped, returned and
		-- ranked at zero. `aggregate` cannot do this (a WHERE on the events table
		-- turns its LEFT JOIN inner and loses eventless games); a leaderboard
		-- groups by an events column, so it has no eventless rows to lose.
		local sideFilter = Fields.roles.sideFilter
		if sideFilter and narrowed[sideFilter] == nil then
			local anySide = false
			for _, column in ipairs(columns) do
				if column.filters and column.filters[sideFilter] ~= nil then
					anySide = true
				end
			end
			if not anySide then
				narrowed[sideFilter] = Fields.sides.maccabiValue
			end
		end
		return narrowed
	end

	--- Rows for one filter set. `options` is this module's own interface and is
	--- therefore English: fields, groupBy, orderBy, having, limit.
	function Queries.query(filters, options)
		options = options or {}
		local query = Queries.build(filters)

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
	function Queries.countFilters(filters, aggregate)
		if type(filters) == 'table' and filters.getParent ~= nil then
			-- Handed a frame instead of a filter set. Without this the frame's own
			-- fields are read as filter names and the error blames a filter called
			-- "args", which sends the reader looking in the wrong place entirely.
			error(NAME .. ': countFilters takes a filter table, not a '
				.. 'frame - from wikitext use {{#invoke:Queries|count|…}}',
				0)
		end
		local rows = Queries.query(filters, {
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
	---   {{#invoke:Queries|count|שחקן=ערן זהבי|קטגוריית מפעל=ליגה}}
	function Queries.count(frame)
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
					NAME .. ': unknown aggregate "%s"', requested), 0)
			end
		end

		-- Same rule as the shim: NULL is an empty cell, never a zero.
		local value = Queries.countFilters(filters, aggregate)
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
					NAME .. ': no entry point declared as "%s"', entryPoint), 0)
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
						NAME .. ': %s does not take "%s" - the template it '
						.. 'replaces has no such parameter', entryPoint, name), 0)
				end
				options[option] = value
			else
				if allowedFilters and not allowedFilters[name]
						and mw.text.trim(tostring(value)) ~= '' then
					error(string.format(
						NAME .. ': %s does not take the filter "%s" - the '
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
	---   {{#invoke:Queries|aggregateProbe|cells=goals:3,assists:4
	---     |שחקן=ערן זהבי|קטגוריית מפעל=ליגה}}
	---
	--- `cells` is name:eventType pairs, comma separated. Diagnostic only - a real
	--- block gets its cells from the block data page, not from wikitext.
	function Queries.aggregateProbe(frame)
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
					NAME .. ': cells must be name:eventType pairs, got "%s"',
					pair), 0)
			end
			cells[#cells + 1] = {
				name = name,
				-- Every cell here filters on מספר אירוע, so it counts EVENTS.
				-- Grain became mandatory after this entry point was written and
				-- nothing tested it, so the probe raised "must declare grain" on
				-- production instead of answering - the one guard this diagnostic
				-- exists to be checked against.
				grain = 'event',
				-- מספר אירוע is a football filter: this probe is football's (its cells
				-- are name:eventType pairs) and raises "unsupported filter" on a
				-- schema without it, which is the right answer there.
				filters = { ['מספר אירוע'] = eventType:gsub(';', ',') },
			}
		end

		local values = Queries.aggregate(shared, cells)
		local output = {}
		for _, cell in ipairs(cells) do
			output[#output + 1] = cell.name .. '=' .. tostring(values[cell.name])
		end
		return table.concat(output, ' ')
	end

	--- Drop-in body for a query template, replacing its whole #cargo_query:
	---   {{#invoke:Queries|gameDataCount}}
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
				NAME .. ': %s reads the calling template\'s parameters, so '
				.. 'it takes none of its own. Put it in a template body as '
				.. '{{#invoke:Queries|%s}}, or use '
				.. '{{#invoke:Queries|count|…}} to pass filters directly.',
				entryPoint, entryPoint), 0)
		end

		return separate(frame:getParent().args, entryPoint)
	end

	--- Drop-in body for תבנית:סטטיסטיקה/שליפות/מתקדמות/כמות אירועי שחקן, the
	--- other query template the display blocks call:
	---   {{#invoke:Queries|playerEventCount}}
	---
	--- It counts events, never games, and its parameter list is its own: asking it
	--- for נתון משחק would answer a question the template it replaces cannot be
	--- asked. Same frame rule as gameDataCount below.
	function Queries.playerEventCount(frame)
		local filters = parentArgumentsOf(frame, 'playerEventCount')
		return string.format(
			'%d', math.floor(Queries.countFilters(filters) + 0.5))
	end

	function Queries.gameDataCount(frame)
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
					NAME .. ': unknown נתון משחק "%s"', requested), 0)
			end
		end

		local value = Queries.countFilters(filters, aggregate)
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

	return Queries
end

return SportQueries
