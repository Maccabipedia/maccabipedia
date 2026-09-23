--[[
Enough of the MediaWiki Lua environment to run Module:FootballQueries outside a
wiki, so the SQL it builds can be asserted in milliseconds instead of by
rendering a page.

A stub, not a mock: mw.ext.cargo.query returns rows this file was told to
return and records what it was asked, and nothing here tries to imitate Cargo's
behaviour beyond that.
]]

local stub = {}

-- Every query the module issued, in order, as { tables, fields, options }.
stub.calls = {}

-- Rows the next queries will return, consumed front to back; when it runs out,
-- queries return no rows.
stub.responses = {}

-- Every extension tag the module emitted, in order, as { name, content, args }.
stub.extensionTags = {}

local PAGES = {
	['Module:FootballQueries/Fields'] =
		'infra/lua_modules/Module_FootballQueries_Fields.lua',
	['Module:FootballStatsBlocks'] =
		'infra/lua_modules/Module_FootballStatsBlocks.lua',
	['Module:SportQueries'] =
		'infra/lua_modules/Module_SportQueries.lua',
	['Module:StatsBlock'] =
		'infra/lua_modules/Module_StatsBlock.lua',
	['Module:BasketballQueries/Fields'] =
		'infra/lua_modules/Module_BasketballQueries_Fields.lua',
	['Module:BasketballQueries'] =
		'infra/lua_modules/Module_BasketballQueries.lua',
	['Module:BasketballStatsBlocks'] =
		'infra/lua_modules/Module_BasketballStatsBlocks.lua',
	['Module:BasketballStatsBlock'] =
		'infra/lua_modules/Module_BasketballStatsBlock.lua',
	['Module:FootballQueries'] =
		'infra/lua_modules/Module_FootballQueries.lua',
	['Module:FootballStatsBlock'] =
		'infra/lua_modules/Module_FootballStatsBlock.lua',
	['Module:FootballSeasonSquad'] =
		'infra/lua_modules/Module_FootballSeasonSquad.lua',
	['Module:SeasonTable'] =
		'infra/lua_modules/Module_SeasonTable.lua',
	['Module:FootballSeasonTable'] =
		'infra/lua_modules/Module_FootballSeasonTable.lua',
	['Module:BasketballSeasonTable'] =
		'infra/lua_modules/Module_BasketballSeasonTable.lua',
	['Module:FootballPlayerStats'] =
		'infra/lua_modules/Module_FootballPlayerStats.lua',
	['Module:SeasonTrophies'] =
		'infra/lua_modules/Module_SeasonTrophies.lua',
	['Module:FootballDate'] =
		'infra/lua_modules/Module_FootballDate.lua',
}

local function loadDataFor(name)
	local paths = PAGES
	local path = paths[name]
	if not path then
		error('stub_mw: no local file registered for ' .. name, 0)
	end

	local chunk, message = loadfile(path)
	if not chunk then
		error('stub_mw: ' .. tostring(message), 0)
	end

	local data = chunk()
	-- A seam for testing guards that a correct schema cannot trigger: the
	-- "column has no declared quote rule" guard needs a filter pointing at an
	-- undeclared column, which the real schema must never contain.
	if stub.dataPatch then
		stub.dataPatch(data)
	end
	if stub.proxyLoadData then
		return stub.asProxy(data)
	end
	return data
end

--- Wraps a table the way mw.loadData does: fields served through a metatable,
--- so `#` reports 0 and ipairs stops at once, while key lookups and pairs
--- work. Code that reads lengths off a loadData result is broken on the wiki
--- and fine in a plain-table test, so the tests need this shape available.
function stub.asProxy(value)
	if type(value) ~= 'table' then
		return value
	end

	local inner = {}
	for key, entry in pairs(value) do
		inner[key] = stub.asProxy(entry)
	end

	local proxy = setmetatable({}, {
		__index = function(_, key)
			return inner[key]
		end,
		__pairs = function()
			return pairs(inner)
		end,
		__len = function()
			return 0
		end,
	})
	-- Lua 5.1 has no __pairs, and Scribunto patches pairs to honour it; the
	-- suite runs on 5.1, so expose the same behaviour through a global pairs
	-- that checks for the metamethod.
	stub.proxies[proxy] = inner
	return proxy
end

function stub.install()
	stub.calls = {}
	stub.responses = {}
	stub.dataPatch = nil
	stub.proxyLoadData = nil
	stub.proxies = {}
	stub.missingPages = {}

	-- Scribunto's pairs honours __pairs; Lua 5.1's does not. The proxy shape
	-- above is only faithful with it, so patch pairs the same way.
	local realPairs = stub.realPairs or pairs
	stub.realPairs = realPairs
	pairs = function(value)
		local inner = stub.proxies and stub.proxies[value]
		if inner then
			return realPairs(inner)
		end
		return realPairs(value)
	end

	-- Scribunto's require takes a wiki page name; Lua's does not. A renderer
	-- that requires the query module needs this to run outside the wiki.
	local realRequire = require
	require = function(name)
		if PAGES[name] then
			return stub.loadModule(name)
		end
		return realRequire(name)
	end

	stub.expanded = {}

	mw = {
		text = {
			trim = function(value)
				return (tostring(value):gsub('^%s+', ''):gsub('%s+$', ''))
			end,
			-- Plain-text split only, which is all the modules use.
			split = function(value, separator)
				local parts, position = {}, 1
				while true do
					local start, stop = tostring(value):find(separator, position, true)
					if not start then
						parts[#parts + 1] = tostring(value):sub(position)
						return parts
					end
					parts[#parts + 1] = tostring(value):sub(position, start - 1)
					position = stop + 1
				end
			end,
		},
		-- A readable stand-in for mw.uri.fullUrl: the page and its query in a
		-- stable order, so a test can assert what the link asks for without
		-- decoding a URL.
		uri = {
			fullUrl = function(page, query)
				local keys = {}
				for key in pairs(query or {}) do
					keys[#keys + 1] = key
				end
				table.sort(keys)
				local parts = {}
				for _, key in ipairs(keys) do
					parts[#parts + 1] = key .. '=' .. tostring(query[key])
				end
				local text = '//wiki/' .. page .. '?' .. table.concat(parts, '&')
				return setmetatable({}, { __tostring = function() return text end })
			end,
		},
		-- Every page exists unless a test lists it in stub.missingPages.
		title = {
			new = function(name)
				return { exists = not stub.missingPages[name] }
			end,
		},
		loadData = loadDataFor,
		ext = {
			cargo = {
				query = function(tables, fields, options)
					stub.calls[#stub.calls + 1] = {
						tables = tables, fields = fields, options = options,
					}
					local rows = table.remove(stub.responses, 1)
					return rows or {}
				end,
			},
		},
	}
end

--- Queue the rows the next query should return.
function stub.willReturn(rows)
	stub.responses[#stub.responses + 1] = rows
end

--- A frame whose parser functions behave like the page's #vardefine / #var:
--- variables persist across calls, as they do for the rest of a page parse.
function stub.newFrame(parentArgs, directArgs)
	stub.variables = {}
	stub.extensionTags = {}
	return stub.newFrameKeepingVariables(parentArgs, directArgs)
end

--- Another frame on the same page: the variables prime set are still there,
--- which is exactly how #vardefine behaves for the rest of a page parse.
function stub.newFrameKeepingVariables(parentArgs, directArgs)
	stub.variables = stub.variables or {}
	local frame
	frame = {
		args = directArgs or {},
		getParent = function()
			return { args = parentArgs or {} }
		end,
		callParserFunction = function(_, name, arguments)
			if name == '#vardefine' then
				-- As the parser does: Variables registers #vardefine without
				-- SFH_OBJECT_ARGS, so every argument is PHP-trimmed before the
				-- extension sees it. A value beginning or ending in whitespace
				-- (a newline included) loses it - which once cost every small
				-- basketball tab its top player.
				stub.variables[arguments[1]] = (tostring(arguments[2]):gsub('^%s+', ''):gsub('%s+$', ''))
				return ''
			end
			if name == '#var' then
				return stub.variables[arguments[1]] or ''
			end
			error('stub_mw: unexpected parser function ' .. tostring(name), 0)
		end,
		expandTemplate = function(_, spec)
			stub.expanded[#stub.expanded + 1] = spec
			-- A visible stand-in: which template, with which positional args.
			return string.format('ROW(%s|%s)', tostring(spec.args[1]),
				tostring(spec.args[2]))
		end,
		extensionTag = function(_, name, content, arguments)
			stub.extensionTags[#stub.extensionTags + 1] = {
				name = name, content = content, args = arguments,
			}
			-- MediaWiki returns a strip marker here and substitutes the tag's
			-- real output later, so the marker's shape is not something a test
			-- can assert against. The stub returns a visible stand-in, and the
			-- tests assert on the recorded content instead.
			return string.format('<%s>%s</%s>', name, content, name)
		end,
	}
	return frame
end

--- Load a fresh copy of a module by its wiki page name, defaulting to the
--- query module. Scribunto's `require` takes page names, so the stub maps them
--- to files the same way mw.loadData does.
function stub.loadModule(page)
	local path = PAGES[page or 'Module:FootballQueries']
	if not path then
		error('stub_mw: no local file registered for ' .. tostring(page), 0)
	end

	local chunk, message = loadfile(path)
	if not chunk then
		error('stub_mw: ' .. tostring(message), 0)
	end
	return chunk()
end

return stub
