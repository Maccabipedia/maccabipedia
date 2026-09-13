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

local PAGES = {
	['Module:FootballQueries/Fields'] =
		'infra/football_queries/Module_FootballQueries_Fields.lua',
	['Module:FootballStatsBlocks'] =
		'infra/football_queries/Module_FootballStatsBlocks.lua',
	['Module:FootballQueries'] =
		'infra/football_queries/Module_FootballQueries.lua',
	['Module:FootballPlayerEvents'] =
		'infra/football_queries/Module_FootballPlayerEvents.lua',
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
	return data
end

function stub.install()
	stub.calls = {}
	stub.responses = {}
	stub.dataPatch = nil

	-- Scribunto's require takes a wiki page name; Lua's does not. A renderer
	-- that requires the query module needs this to run outside the wiki.
	local realRequire = require
	require = function(name)
		if PAGES[name] then
			return stub.loadModule(name)
		end
		return realRequire(name)
	end

	mw = {
		text = {
			trim = function(value)
				return (tostring(value):gsub('^%s+', ''):gsub('%s+$', ''))
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
