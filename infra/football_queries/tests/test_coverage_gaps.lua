--[[
Tests for everything the first suite let through.

A reviewer ran 18 mutations against Module:FootballQueries and 10 stayed green.
Each test here kills one of them. The list is in .claude/tmp/design_review.md;
the lesson is in the file header of the other suite: a green first run is not
evidence, and "I mutated two things" does not generalise to a suite that bites.

Run from the repository root:
    lua5.1 infra/football_queries/tests/test_coverage_gaps.lua
]]

package.path = 'infra/football_queries/tests/?.lua;' .. package.path
local stub = require('stub_mw')

local passed, failed = 0, 0

local function check(name, body)
	stub.install()
	local ok, message = pcall(body, stub.loadModule())
	if ok then
		passed = passed + 1
	else
		failed = failed + 1
		print(string.format('FAIL  %s\n        %s', name, tostring(message)))
	end
end

local function equals(actual, expected, what)
	if actual ~= expected then
		error(string.format('%s\n        expected: %s\n        actual:   %s',
			what or 'mismatch', tostring(expected), tostring(actual)), 0)
	end
end

local function expectError(pattern, body)
	local ok, message = pcall(body)
	if ok then
		error('expected an error, none raised', 0)
	end
	if not tostring(message):find(pattern, 1, true) then
		error(string.format('error did not mention "%s": %s',
			pattern, tostring(message)), 0)
	end
end

-- M1: the headline guard in the design was never tested. A correct schema
-- cannot trigger it, so the stub adds a filter pointing at a column that has
-- no declared rule - exactly the mistake the guard exists to catch.
check('a column with no declared quote rule raises', function()
	stub.install()
	stub.dataPatch = function(data)
		data.filters['קהל'] = { column = 'Football_Games.Crowd', kind = 'text' }
	end
	local FootballQueries = stub.loadModule()

	expectError('no quote rule declared', function()
		FootballQueries.build({ ['קהל'] = '20000' })
	end)
end)

-- M2: every competition category, not just ליגה.
check('each קטגוריית מפעל maps to its own flag', function(FootballQueries)
	local expected = {
		['ליגה'] = 'Competitions.League = 1',
		['גביע'] = 'Competitions.Trophy = 1',
		['בינלאומי'] = 'Competitions.International = 1',
		['רשמי'] = 'Competitions.Official = 1',
	}
	for value, condition in pairs(expected) do
		equals(FootballQueries.build({ ['קטגוריית מפעל'] = value }).where,
			condition, value)
	end
end)

-- M3: only ניצחון was asserted, so a draw/loss swap was invisible.
check('every תוצאה word maps to its own ResultOpt', function(FootballQueries)
	local expected = { ['ניצחון'] = 1, ['תיקו'] = 2, ['הפסד'] = 3 }
	for word, resultOpt in pairs(expected) do
		equals(FootballQueries.build({ ['תוצאה'] = word }).where,
			'Football_Games.ResultOpt = ' .. resultOpt, word)
	end
end)

-- M4: three filters were repointable to the wrong column undetected.
check('every declared filter targets its own column', function(FootballQueries)
	local expected = {
		{ ['תת אירוע'] = '3' , where = 'Games_Events.SubType IN (3)' },
		{ ['תוצאה מכבי'] = '2', where = 'Football_Games.ResultMaccabi = 2' },
		{ ['תוצאה יריבה'] = '1', where = 'Football_Games.ResultOpponent = 1' },
		{ ['אצטדיונים'] = 'בלומפילד',
		  where = 'Football_Games.Stadium IN ("בלומפילד")' },
		{ ['מפעלים'] = 'ליגת העל',
		  where = 'Football_Games.Competition IN ("ליגת העל")' },
		{ ['עונה'] = '2021/22', where = 'Football_Games.Season = "2021/22"' },
		{ ['מאמן'] = 'אבי נמני',
		  where = 'Football_Games.CoachMaccabi = "אבי נמני"' },
		{ ['שופט'] = 'ג\'ון ביטון', where = 'Football_Games.Refs = "ג\'ון ביטון"' },
		{ ['ביתחוץ'] = 'בית', where = 'Football_Games.HomeAway = "בית"' },
		{ ['סט מדים'] = 'לבן',
		  where = 'Football_Games_Uniforms.KitName = "לבן"' },
		{ ['מפעל נוכחי'] = 'ליגת העל',
		  where = 'Competitions.CurrentName = "ליגת העל"' },
		{ ['מפעל מקורי'] = 'ליגה לאומית',
		  where = 'Competitions.OriginalName = "ליגה לאומית"' },
	}
	for _, case in ipairs(expected) do
		local where = case.where
		local filters = {}
		for name, value in pairs(case) do
			if name ~= 'where' then
				filters[name] = value
			end
		end
		local built = FootballQueries.build(filters)
		-- Events filters also pick up the Team default; compare the prefix.
		local actual = built.where:gsub(' AND Games_Events%.Team = 1$', '')
		equals(actual, where, where)
	end
end)

-- M5: ללא תת אירוע inverting was invisible.
check('ללא תת אירוע excludes rather than selects', function(FootballQueries)
	local query = FootballQueries.build({ ['ללא תת אירוע'] = '33' })
	equals(query.where,
		'Games_Events.SubType != 33 AND Games_Events.Team = 1', 'where')
end)

-- M6: the opponent alias path had no assertion on its query at all.
check('the opponent alias query matches and returns the right columns',
	function(FootballQueries)
		stub.willReturn({ { name = 'הפועל תל אביב' }, { name = 'הפועל ת"א' } })
		local query = FootballQueries.build({ ['יריבה'] = 'הפועל תל אביב' })
		local call = stub.calls[1]
		equals(call.tables, 'Opponents=o1,Opponents=o2', 'tables')
		equals(call.fields, 'o2.OriginalName=name', 'fields')
		equals(call.options.join, 'o1.CanonicalName = o2.CanonicalName', 'join')
		equals(call.options.where, 'o1.OriginalName = "הפועל תל אביב"', 'where')
		-- Games store the stripped form, so the returned names are stripped.
		equals(query.where,
			'Football_Games.Opponent IN ("הפועל תל אביב", "הפועל תא")', 'in')
	end)

check('the stadium alias query matches and returns the right columns',
	function(FootballQueries)
		stub.willReturn({ { name = 'אצטדיון בלומפילד' } })
		FootballQueries.build({ ['אצטדיון'] = 'בלומפילד' })
		local call = stub.calls[1]
		equals(call.fields, 's2.CanonicalName=name', 'fields')
		equals(call.options.join, 's1._pageID = s2._pageID', 'join')
		equals(call.options.where, 's1.CanonicalName = "בלומפילד"', 'where')
	end)

-- M7: a literal double quote is escaped, not refused. Opponents really stores
-- בית"ר ירושלים, and refusing it made every Beitar query a hard error.
check('a literal double quote is escaped for a quote-keeping column',
	function(FootballQueries)
		stub.willReturn({ { name = 'בית"ר ירושלים' } })
		local query = FootballQueries.build({ ['יריבה'] = 'בית"ר ירושלים' })
		equals(stub.calls[1].options.where,
			'o1.OriginalName = "בית\\"ר ירושלים"', 'escaped in lookup')
		equals(query.where,
			'Football_Games.Opponent IN ("ביתר ירושלים")', 'stripped for games')
	end)

-- Football_Games.Competition is the column §16 got wrong: it KEEPS quotes, and
-- גביע מלצ'ט is the one value that proves it.
check('a competition name keeps its apostrophe', function(FootballQueries)
	equals(FootballQueries.build({ ['מפעלים'] = "גביע מלצ'ט" }).where,
		'Football_Games.Competition IN ("גביע מלצ\'ט")', 'kept')
end)

check('a quote-bearing stadium name is stripped for the games column',
	function(FootballQueries)
		stub.willReturn({ { name = 'אצטדיון בלומ"פילד' } })
		equals(FootballQueries.build({ ['אצטדיון'] = 'בלומפילד' }).where,
			'Football_Games.Stadium IN ("אצטדיון בלומפילד")', 'stripped')
	end)

check('a backslash is escaped before the quotes are', function(FootballQueries)
	local query = FootballQueries.build({ ['שחקן'] = 'a\\b"c' })
	equals(query.where,
		'Games_Events.PlayerName = "a\\\\b\\"c" AND Games_Events.Team = 1',
		'where')
end)

-- M8: every entity form, not only &#34;.
check('all four quote entities are normalised', function(FootballQueries)
	for _, entity in ipairs({ '&#34;', '&quot;', '&#39;', '&apos;' }) do
		local query = FootballQueries.build({ ['יריבות'] = 'בית' .. entity .. 'ר' })
		equals(query.where, 'Football_Games.Opponent IN ("ביתר")', entity)
	end
end)

-- Cargo decodes entities in the WHERE clause AFTER this module escapes it, so
-- an entity spelling the module does not know becomes a raw quote inside the
-- SQL. This exact value returned every row in the table on production.
-- The payload that returned every row on production. Decoded to literal
-- quotes, which the column rule then strips, so nothing reaches the SQL as a
-- quote. The condition below is inert, not an injection.
check('the proven injection payload becomes an inert literal',
	function(FootballQueries)
		equals(FootballQueries.build({
			['יריבות'] = 'x&#x22; OR 1=1 OR &#x22;',
		}).where, 'Football_Games.Opponent IN ("x OR 1=1 OR ")', 'defanged')
	end)

-- The catch-all: a spelling the table does not know must not reach Cargo,
-- which would decode it back into a quote inside the query.
check('an unknown entity spelling raises instead of reaching Cargo',
	function(FootballQueries)
		for _, payload in ipairs({ 'x&#0034; OR 1=1', 'x&#X0022; OR 1=1',
		                           'x&QUOT; OR 1=1' }) do
			expectError('contains an ampersand', function()
				FootballQueries.build({ ['יריבות'] = payload })
			end)
		end
	end)

check('every quote entity spelling is decoded, including hex',
	function(FootballQueries)
		for _, entity in ipairs({ '&#34;', '&#x22;', '&#X22;', '&quot;',
		                          '&#39;', '&#x27;', '&#X27;', '&apos;' }) do
			local query = FootballQueries.build({
				['יריבות'] = 'בית' .. entity .. 'ר',
			})
			equals(query.where, 'Football_Games.Opponent IN ("ביתר")', entity)
		end
	end)

check('a bare ampersand raises rather than reaching the query',
	function(FootballQueries)
		expectError('contains an ampersand', function()
			FootballQueries.build({ ['שחקן'] = 'A&B' })
		end)
	end)

-- The drop-in used to accept every filter the layer knows, so a player name
-- would join the events table and return an EVENT count where the call site
-- says "number of games" - no error, plausible number, wrong number.
check('the game-count shim refuses a filter its template never had',
	function(FootballQueries)
		local frame = { args = {}, getParent = function()
			return { args = { ['שחקן'] = 'ערן זהבי', ['עונה'] = '2021/22' } }
		end }
		expectError('does not take the filter "שחקן"', function()
			FootballQueries.gameDataCount(frame)
		end)
	end)

check('the game-count shim refuses an option its template never had',
	function(FootballQueries)
		local frame = { args = {}, getParent = function()
			return { args = { ['עונה'] = '2021/22', ['הגבלה'] = '10' } }
		end }
		expectError('does not take "הגבלה"', function()
			FootballQueries.gameDataCount(frame)
		end)
	end)

check('the game-count shim still takes every filter its template had',
	function(FootballQueries)
		stub.willReturn({ { n = '5' } })
		local frame = { args = {}, getParent = function()
			return { args = {
				['עונה'] = '2021/22', ['קטגוריית מפעל'] = 'ליגה',
				['מאמן'] = 'אבי נמני', ['אצטדיון'] = '', ['יריבות'] = '',
				['תוצאה'] = 'ניצחון', ['סט מדים'] = '', ['שופט'] = '',
			} }
		end }
		equals(FootballQueries.gameDataCount(frame), '5', 'accepted')
	end)

-- M9: the rounding test used 150.0000, where floor, ceil and round agree.
check('SUM is rounded half-up, not truncated', function(FootballQueries)
	stub.willReturn({ { n = '150.5' } })
	local frame = { args = {}, getParent = function()
		return { args = { ['נתון משחק'] = 'כיבושים' } }
	end }
	equals(FootballQueries.gameDataCount(frame), '151', 'half-up')

	stub.install()
	stub.willReturn({ { n = '150.4' } })
	equals(FootballQueries.gameDataCount(frame), '150', 'below the half')
end)

-- M10: both remaining guards were untested.
check('a limit above maxLimit raises', function(FootballQueries)
	expectError('exceeds maxLimit', function()
		FootballQueries.query({ ['עונה'] = '2021/22' }, { limit = 99999 })
	end)
end)

check('an empty IN list raises rather than emitting IN ()',
	function(FootballQueries)
		expectError('no values to match', function()
			FootballQueries.build({ ['יריבות'] = ' , , ' })
		end)
	end)

-- B-class: crashes on live call sites.
-- The date VALUE is pre-quoted by real callers too: the template requires it,
-- and the 366 calendar pages pass `תאריך="2021-03-15"` through a variable.
-- Unquoted, the template silently returns 0.
check('a pre-quoted date value is accepted, not double-quoted',
	function(FootballQueries)
		local expected = 'DATE_FORMAT("2021-03-15", "%d-%m")'
			.. ' = DATE_FORMAT(Football_Games.Date, "%d-%m")'
		equals(FootballQueries.build({
			['תאריך'] = '"2021-03-15"', ['פורמט תאריך'] = '"%d-%m"',
		}).where, expected, 'quoted value')
		equals(FootballQueries.build({
			['תאריך'] = '2021-03-15', ['פורמט תאריך'] = '"%d-%m"',
		}).where, expected, 'bare value')
	end)

check('פורמט תאריך is accepted with the quotes real call sites send',
	function(FootballQueries)
		local expected = 'DATE_FORMAT("2021-08-22", "%d-%m")'
			.. ' = DATE_FORMAT(Football_Games.Date, "%d-%m")'
		equals(FootballQueries.build({
			['תאריך'] = '2021-08-22', ['פורמט תאריך'] = '"%d-%m"',
		}).where, expected, 'quoted')
		equals(FootballQueries.build({
			['תאריך'] = '2021-08-22', ['פורמט תאריך'] = '%d-%m',
		}).where, expected, 'bare')
	end)

check('an unsafe date format is still refused once unquoted',
	function(FootballQueries)
		expectError('unsafe פורמט תאריך', function()
			FootballQueries.build({
				['תאריך'] = '2021-08-22',
				['פורמט תאריך'] = '"%Y\\") OR 1=1 -- "',
			})
		end)
	end)

check('a positional parameter names itself instead of dying in table.sort',
	function(FootballQueries)
		expectError('positional parameter', function()
			FootballQueries.build({ ['עונה'] = '2021/22', [1] = 'בית' })
		end)
	end)

check('a limit arriving as wikitext text is coerced', function(FootballQueries)
	stub.willReturn({ { n = '5' } })
	FootballQueries.query({ ['עונה'] = '2021/22' }, { limit = '250' })
	equals(stub.calls[1].options.limit, 250, 'coerced')
end)

check('a non-numeric limit raises', function(FootballQueries)
	expectError('הגבלה must be a number', function()
		FootballQueries.query({ ['עונה'] = '2021/22' }, { limit = 'כמה' })
	end)
end)

check('an aggregate from wikitext cannot reach the field list',
	function(FootballQueries)
		expectError('unknown aggregate', function()
			FootballQueries.count({
				args = { aggregate = 'COUNT(*)) OR 1=1 -- ' },
			})
		end)
	end)

print(string.format('\n%d passed, %d failed', passed, failed))
os.exit(failed > 0 and 1 or 0)
