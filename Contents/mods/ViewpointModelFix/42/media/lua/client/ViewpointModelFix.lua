-- Gives Viewpoint real models for the sprites it draws badly (urinals, toilets, sinks).
--
-- Nothing needs setting up: every square the game loads is checked for sprites whose name
-- (CustomName / GroupName) matches a model, and those get bound through extra pack files this
-- mod writes into its own folder and registers with Viewpoint as it goes. What it found is
-- remembered in Zomboid/Lua/ViewpointModelFix_learned.txt, so the next start binds it at once.
--
-- F7 still lists the sprites round the player into Zomboid/Lua/ViewpointModelFix_binds.txt.

ViewpointModelFix = ViewpointModelFix or {}

local MOD_ID = "ViewpointModelFix"
local MANIFEST = "media/viewpoint/ViewpointModelFix/pack.txt"
local PACK_DIR = "viewpoint/ViewpointModelFix/"
local LEARNED_FILE = "ViewpointModelFix_learned.txt"
local DUMP_FILE = "ViewpointModelFix_binds.txt"
local DUMP_RADIUS = 3
local MODELS = { "urinal", "toilet", "sink", "shelf_metal", "box_small" }

-- Turn per sprite facing, in degrees. The models face south with their back to a north wall.
-- If they all come out backwards or sideways in game, this table is the one place to fix it
-- (then delete Zomboid/Lua/ViewpointModelFix_learned.txt so the old turns are forgotten).
ViewpointModelFix.DEGREES = { S = 0, W = 90, N = 180, E = 270 }

-- Which model a sprite gets, matched against its CustomName / GroupName (lower case).
-- auto = false: only listed by F7, never bound on its own (the shelf model is empty, the
-- sprite's art has the shelf's goods painted on, so swapping it is a matter of taste).
ViewpointModelFix.MATCHES = {
    { find = "urinal", model = "urinal", auto = true },
    { find = "toilet", model = "toilet", auto = true },
    { find = "sink", model = "sink", auto = true, wallOnly = true },
    { find = "metal shel", model = "shelf_metal", auto = false },
    { find = "shelves", model = "shelf_metal", auto = false },
    { find = "cardboard", model = "box_small", auto = false },
}

local function log(text)
    print("[ViewpointModelFix] " .. text)
end

local function viewpointPacks()
    local packs = Viewpoint and Viewpoint.ModelPacks
    if packs and packs.register then return packs end
    return nil
end

-- the base pack: the models, no binds -------------------------------------------------------

local registered = false

local function register()
    if registered then return end
    local packs = viewpointPacks()
    if not packs then return end
    local ok, result = pcall(packs.register, MOD_ID, MANIFEST)
    if ok and result then
        registered = true
        log("model pack registered")
    elseif not ok then
        log("registering the model pack failed: " .. tostring(result))
    end
end

ViewpointModelFix.register = register

-- reading sprites ---------------------------------------------------------------------------

local function prop(props, key)
    if not props then return nil end
    for _, getter in ipairs({ "Val", "get" }) do
        local ok, value = pcall(function() return props[getter](props, key) end)
        if ok and value ~= nil and value ~= "" then return tostring(value) end
    end
    return nil
end

local function has(props, key)
    if not props then return false end
    local ok, value = pcall(function() return props:Is(key) end)
    return ok and value == true
end

local function describe(sprite)
    local props = sprite:getProperties()
    local custom, group = prop(props, "CustomName"), prop(props, "GroupName")
    local text = string.lower((custom or "") .. " " .. (group or ""))
    local match
    for _, m in ipairs(ViewpointModelFix.MATCHES) do
        if string.find(text, m.find, 1, true) then
            match = m
            break
        end
    end
    -- a sink set into a kitchen counter is a counter first: leave it be
    if match and match.wallOnly and (prop(props, "container") or has(props, "IsTable")
            or string.find(text, "kitchen", 1, true) or string.find(text, "counter", 1, true)) then
        match = nil
    end
    return {
        custom = custom,
        group = group,
        facing = prop(props, "Facing"),
        match = match,
    }
end

local function bindValue(info)
    local degrees = ViewpointModelFix.DEGREES[info.facing or "S"] or 0
    return string.format("%s,%d,0,0,0,1", info.match.model, degrees)
end

-- learning and binding as squares load ------------------------------------------------------

local checked = {}   -- sprite name -> true once looked at
local learned = {}   -- sprite name -> bind value, kept across starts
local applied = {}   -- sprite name -> true once in a registered pack this session
local pending = {}   -- sprite names learned but not yet registered
local queued = {}    -- sprite name -> true while in pending
local batch = 0
local writeAt         -- where getModFileWriter puts files, found on first use

local function readLearned()
    local ok, reader = pcall(getFileReader, LEARNED_FILE, false)
    if not ok or not reader then return end
    local line = reader:readLine()
    while line do
        local name, value = string.match(line, "^([^#=%s][^=]*)=(.+)$")
        if name then learned[name] = value end
        line = reader:readLine()
    end
    reader:close()
end

local function writeLearned()
    local names = {}
    for name in pairs(learned) do table.insert(names, name) end
    table.sort(names)
    local writer = getFileWriter(LEARNED_FILE, true, false)
    writer:writeln("# sprites ViewpointModelFix found and bound: <sprite>=<model>,<degrees>,<x>,<y>,<z>,<scale>")
    writer:writeln("# delete this file to have them found again")
    for _, name in ipairs(names) do writer:writeln(name .. "=" .. learned[name]) end
    writer:close()
end

local function modFileExists(path)
    local ok, reader = pcall(getModFileReader, MOD_ID, path, false)
    if ok and reader then
        reader:close()
        return true
    end
    return false
end

-- getModFileWriter's paths start from the mod's root, its version folder or its common folder
-- depending on the game's build; find which by looking for a file we know is there
local function findWriteAt()
    if writeAt ~= nil then return writeAt end
    if modFileExists("42/media/" .. PACK_DIR .. "pack.txt") then
        writeAt = { dir = "42/media/" .. PACK_DIR, models = "" }
    elseif modFileExists("media/" .. PACK_DIR .. "pack.txt") then
        writeAt = { dir = "media/" .. PACK_DIR, models = "" }
    elseif modFileExists("mod.info") then
        writeAt = { dir = "media/" .. PACK_DIR, models = "../../../../42/media/" .. PACK_DIR }
    else
        writeAt = false
        log("could not find the mod's own folder to write its binds into")
    end
    return writeAt
end

local function flush()
    if #pending == 0 then return end
    local packs = viewpointPacks()
    local at = findWriteAt()
    if not packs or not at then return end

    batch = batch + 1
    local file = string.format("auto_%d.txt", batch)
    local writer = getModFileWriter(MOD_ID, at.dir .. file, true, false)
    if not writer then
        log("could not write " .. at.dir .. file)
        return
    end
    writer:writeln("# written by ViewpointModelFix.lua; rewritten every start")
    writer:writeln(string.format("id=ViewpointModelFix-auto-%d", batch))
    writer:writeln(string.format("name=Model fixes (found %d)", batch))
    for _, model in ipairs(MODELS) do
        writer:writeln(string.format("model.%s=%s%s.obj", model, at.models, model))
    end
    for _, name in ipairs(pending) do
        writer:writeln("bind." .. name .. "=" .. learned[name])
    end
    writer:close()

    local ok, result = pcall(packs.register, MOD_ID, "media/" .. PACK_DIR .. file)
    if ok and result then
        for _, name in ipairs(pending) do
            applied[name] = true
            queued[name] = nil
        end
        log(string.format("bound %d sprites (%s)", #pending, file))
        pending = {}
        writeLearned()
    else
        -- don't try again every minute: one line in the log says what went wrong
        writeAt = false
        log(string.format("Viewpoint did not take %s: %s", file, tostring(result)))
    end
end

ViewpointModelFix.flush = flush

local function queue(name)
    if applied[name] or queued[name] then return end
    queued[name] = true
    table.insert(pending, name)
end

local function learn(name, value)
    learned[name] = value
    queue(name)
end

local function check(sprite)
    local name = sprite and sprite:getName()
    if not name or checked[name] then return end
    checked[name] = true
    if learned[name] then return end
    local info = describe(sprite)
    if info.match and info.match.auto then learn(name, bindValue(info)) end
end

local function onSquare(square)
    local objects = square and square:getObjects()
    if not objects then return end
    for i = 0, objects:size() - 1 do
        check(objects:get(i):getSprite())
    end
end

local function safeOnSquare(square)
    local ok, err = pcall(onSquare, square)
    if not ok then log("checking a square failed: " .. tostring(err)) end
end

local function onGameStart()
    register()
    for name in pairs(learned) do queue(name) end
    flush()
end

-- F7: list what is round the player ---------------------------------------------------------

function ViewpointModelFix.dump()
    local player = getPlayer()
    if not player then return end
    local cell = getCell()
    local px, py, pz = math.floor(player:getX()), math.floor(player:getY()), math.floor(player:getZ())

    local seen, lines, bound = {}, {}, 0
    for x = px - DUMP_RADIUS, px + DUMP_RADIUS do
        for y = py - DUMP_RADIUS, py + DUMP_RADIUS do
            local square = cell:getGridSquare(x, y, pz)
            local objects = square and square:getObjects()
            if objects then
                for i = 0, objects:size() - 1 do
                    local sprite = objects:get(i):getSprite()
                    local name = sprite and sprite:getName()
                    if name and not seen[name] then
                        seen[name] = true
                        local info = describe(sprite)
                        local about = string.format("%s / %s, facing %s",
                            info.custom or "?", info.group or "?", info.facing or "?")
                        if learned[name] then
                            bound = bound + 1
                            table.insert(lines, string.format("bound:    %s=%s   # %s", name, learned[name], about))
                        elseif info.match then
                            table.insert(lines, string.format("bind.%s=%s   # %s", name, bindValue(info), about))
                        else
                            table.insert(lines, string.format("# no model: %s   (%s)", name, about))
                        end
                    end
                end
            end
        end
    end
    table.sort(lines)

    local writer = getFileWriter(DUMP_FILE, true, true)
    writer:writeln(string.format("# round %d,%d,%d", px, py, pz))
    for _, line in ipairs(lines) do
        writer:writeln(line)
        log(line)
    end
    writer:close()

    player:Say(string.format("%d sprites, %d bound: Zomboid/Lua/%s", #lines, bound, DUMP_FILE))
end

local function onKey(key)
    if key == Keyboard.KEY_F7 then ViewpointModelFix.dump() end
end

readLearned()
register()
Events.OnGameBoot.Add(register)
Events.LoadGridsquare.Add(safeOnSquare)
Events.OnGameStart.Add(onGameStart)
Events.EveryOneMinute.Add(flush)
Events.OnKeyPressed.Add(onKey)
