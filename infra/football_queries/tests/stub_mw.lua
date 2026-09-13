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

local function loadDataFor(name)
	local paths = {
		['Module:FootballQueries/Fields'] =
			'infra/football_queries/Module_FootballQueries_Fields.lua',
	}
	local path = paths[name]
	if not path then
		error('stub_mw: no local file registered for ' .. name, 0)
	end

	local chunk, message = loadfile(path)
	if not chunk then
		error('stub_mw: ' .. tostring(message), 0)
	end
	return chunk()
end

function stub.install()
	stub.calls = {}
	stub.responses = {}

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

--- Load a fresh copy of the module under test.
function stub.loadModule()
	local chunk, message = loadfile(
		'infra/football_queries/Module_FootballQueries.lua')
	if not chunk then
		error('stub_mw: ' .. tostring(message), 0)
	end
	return chunk()
end

return stub
