-- Gives Viewpoint real models for the sprites it draws badly (urinals, toilets, sinks, beds,
-- mirrors, light switches, hand dryers, metal shelving and the goods stocked on it).
--
-- Nothing needs setting up: every square the game loads is checked for sprites whose name
-- (CustomName / GroupName) matches a model, and those get bound through extra pack files this
-- mod writes into its own folder and registers with Viewpoint as it goes. What it found is
-- remembered in Zomboid/Lua/ViewpointModelFix_learned.txt, so the next start binds it at once.
--
-- F7 lists the sprites round the player into Zomboid/Lua/ViewpointModelFix_binds.txt;
-- Shift+F7 reloads the models from disk without restarting the game.

ViewpointModelFix = ViewpointModelFix or {}

local MOD_ID = "ViewpointModelFix"
local MANIFEST = "media/viewpoint/ViewpointModelFix/pack.txt"
local PACK_DIR = "viewpoint/ViewpointModelFix/"
local LEARNED_FILE = "ViewpointModelFix_learned.txt"
local DUMP_FILE = "ViewpointModelFix_binds.txt"
local DUMP_RADIUS = 3
local MODELS = { "urinal", "toilet", "sink", "shelf_metal", "box_small",
    "bed", "bed_blue", "bed_red", "bed_green",
    "bed_head", "bed_blue_head", "bed_red_head", "bed_green_head",
    "mirror", "light_switch", "hand_dryer",
    "goods_store_1", "goods_store_2", "goods_store_3",
    "goods_storage_1", "goods_storage_2", "goods_storage_3" }

-- Turn per sprite facing, in degrees. The models face south with their back to a north wall.
-- If they all come out backwards or sideways in game, this table is the one place to fix it;
-- sprites learned with the old turns are bound again as they load.
ViewpointModelFix.DEGREES = { S = 0, W = 90, N = 180, E = 270 }

-- A bed's head is the tile at its back, away from where it faces. If pillows come out at the
-- foot of every bed, set this to false.
ViewpointModelFix.PILLOW_AT_BACK = true

-- Goods on a shelf in a room, or with a name, holding one of these words are storeroom stock
-- (boxes, paint tins); anything else is shop stock (cans, bottles, jars, packets).
ViewpointModelFix.STORAGE_WORDS = { "storage", "warehouse", "garage", "shed", "factory", "industr",
    "tool", "stock", "crate", "box", "janitor", "garden", "farm", "barn", "mechanic" }

-- Which model a sprite gets, matched against its CustomName / GroupName (lower case): the
-- first entry whose `custom` is the whole CustomName (when given) and whose `find` is in
-- "<custom> <group>" (when given) wins.
-- skip: words that rule the entry out. auto = false: only listed by F7, never bound on its own.
ViewpointModelFix.MATCHES = {
    -- beds come in two halves, one sprite per tile: the head gets "<model>_head" (bed = true)
    { custom = "bed", find = "blue", model = "bed_blue", auto = true, bed = true },
    { custom = "bed", find = "red", model = "bed_red", auto = true, bed = true },
    { custom = "bed", find = "pink", model = "bed_red", auto = true, bed = true },
    { custom = "bed", find = "green", model = "bed_green", auto = true, bed = true },
    { custom = "bed", model = "bed", auto = true, bed = true },
    -- wall = true: turned by the wall the sprite hangs on, before its Facing
    { find = "mirror", model = "mirror", auto = true, wall = true },
    { custom = "switch", model = "light_switch", auto = true, wall = true },
    { find = "blower", model = "hand_dryer", auto = true, wall = true },
    { find = "urinal", model = "urinal", auto = true },
    { find = "toilet hanging", model = "urinal", auto = true },   -- the game's urinals; "Sink / Hanging" is a sink
    { find = "toilet", model = "toilet", auto = true },
    { find = "sink", model = "sink", auto = true, wallOnly = true },
    -- shelving: the empty rack; the goods the game draws over a stocked one (an overlay sprite,
    -- gone when it is emptied) get a goods model of their own (goods = true)
    { find = "shel", model = "shelf_metal", auto = true, goods = true,
      skip = { "wood", "book", "small", "wall", "corner", "glass", "fridge", "freezer", "display",
               "counter", "spice", "magazine", "shoe", "cloth", "rack" } },
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

-- Build 42 renamed some PropertyContainer methods; find the ones this build has once, so
-- nothing is ever called that isn't there (a failed call logs a stack trace even under pcall)
local methods = {}

local function method(props, names)
    local key = table.concat(names, "/")
    if methods[key] == nil then
        methods[key] = false
        for _, name in ipairs(names) do
            local ok, found = pcall(function() return props[name] end)
            if ok and found ~= nil then
                methods[key] = name
                break
            end
        end
    end
    return methods[key]
end

local function prop(props, key)
    if not props then return nil end
    local name = method(props, { "get", "Val" })
    if not name then return nil end
    local value = props[name](props, key)
    if value == nil or value == "" then return nil end
    return tostring(value)
end

-- flags are asked for by the game's own IsoFlagType where Lua can see it; a flag the build
-- doesn't take is never asked for again
local badFlags = {}

local function has(props, key)
    if not props or badFlags[key] then return false end
    local name = method(props, { "has", "Is" })
    if not name then return false end
    local flag = key
    if IsoFlagType and IsoFlagType[key] ~= nil then flag = IsoFlagType[key] end
    local ok, value = pcall(function() return props[name](props, flag) end)
    if not ok then
        badFlags[key] = true
        return false
    end
    return value == true
end

-- wall decorations often carry no Facing, only the wall they hang on
local ATTACHED = { attachedN = "S", attachedW = "E", attachedS = "N", attachedE = "W" }

local function attachedFacing(props)
    for flag, faces in pairs(ATTACHED) do
        if has(props, flag) then return faces end
    end
    return nil
end

local function facingOf(props, wall)
    if wall then return attachedFacing(props) or prop(props, "Facing") end
    return prop(props, "Facing") or attachedFacing(props)
end

local function matches(m, custom, text)
    if m.custom and string.lower(custom or "") ~= m.custom then return false end
    if m.find and not string.find(text, m.find, 1, true) then return false end
    for _, word in ipairs(m.skip or {}) do
        if string.find(text, word, 1, true) then return false end
    end
    return true
end

-- Which end of a bed a sprite is, from the sprite grid big furniture is laid out on: "head",
-- "foot", or nil when the build or the bed doesn't say.
local gridBroken = false

local function bedPart(sprite, facing)
    if gridBroken or not method(sprite, { "getSpriteGrid" }) then return nil end
    local ok, gx, gy, w, h = pcall(function()
        local grid = sprite:getSpriteGrid()
        if not grid then return nil end
        return grid:getSpriteGridPosX(sprite), grid:getSpriteGridPosY(sprite), grid:getWidth(), grid:getHeight()
    end)
    if not ok then
        gridBroken = true
        return nil
    end
    if not gx then return nil end
    local back
    if facing == "S" and h > 1 then back = gy == 0
    elseif facing == "N" and h > 1 then back = gy == h - 1
    elseif facing == "E" and w > 1 then back = gx == 0
    elseif facing == "W" and w > 1 then back = gx == w - 1
    else return nil end
    if not ViewpointModelFix.PILLOW_AT_BACK then back = not back end
    return back and "head" or "foot"
end

local function describe(sprite)
    local props = sprite:getProperties()
    local custom, group = prop(props, "CustomName"), prop(props, "GroupName")
    local text = string.lower((custom or "") .. " " .. (group or ""))
    local match
    for _, m in ipairs(ViewpointModelFix.MATCHES) do
        if matches(m, custom, text) then
            match = m
            break
        end
    end
    -- a sink set into a kitchen counter is a counter first: leave it be
    if match and match.wallOnly and (prop(props, "container") or has(props, "IsTable")
            or string.find(text, "kitchen", 1, true) or string.find(text, "counter", 1, true)) then
        match = nil
    end
    local facing = facingOf(props, match and match.wall)
    return {
        custom = custom,
        group = group,
        facing = facing,
        match = match,
        part = match and match.bed and bedPart(sprite, facing) or nil,
    }
end

local function degreesOf(info)
    return ViewpointModelFix.DEGREES[info.facing or "S"] or 0
end

local function bindValue(info)
    local model = info.match.model
    if info.part == "head" then model = model .. "_head" end
    return string.format("%s,%d,0,0,0,1", model, degreesOf(info))
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
    writer:writeln("# rebuilt as the map loads; deleting it is safe")
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
-- depending on the game's build (and need not match getModFileReader's). The models ship in
-- both 42/ and common/, so a pack file written to either finds them beside it.
local function findWriteAt()
    if writeAt ~= nil then return writeAt end
    -- dir: where getModFileWriter puts pack files; read: where getModFileReader finds the models
    if modFileExists("42/media/" .. PACK_DIR .. "pack.txt") then
        writeAt = { dir = "42/media/" .. PACK_DIR, read = "42/media/" .. PACK_DIR }
    elseif modFileExists("media/" .. PACK_DIR .. "pack.txt") then
        writeAt = { dir = "media/" .. PACK_DIR, read = "media/" .. PACK_DIR }
    elseif modFileExists("mod.info") then
        writeAt = { dir = "media/" .. PACK_DIR, read = "media/" .. PACK_DIR }
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
        writer:writeln(string.format("model.%s=%s.obj", model, model))
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
    if learned[name] == value then return end
    learned[name] = value
    applied[name] = nil
    queue(name)
end

local goodsShelf = {}       -- shelf sprite name -> its turn, for shelves whose goods get a model
local checkedOverlay = {}   -- overlay sprite name -> true once looked at

local function check(sprite)
    local name = sprite and sprite:getName()
    if not name or checked[name] then return end
    checked[name] = true
    local info = describe(sprite)
    if not (info.match and info.match.auto) then return end
    if info.match.goods then goodsShelf[name] = degreesOf(info) end
    learn(name, bindValue(info))
end

local function goodsKind(overlay, square)
    local text = string.lower(overlay)
    local ok, room = pcall(function()
        local r = square and square:getRoom()
        return r and r:getName()
    end)
    if ok and room then text = text .. " " .. string.lower(tostring(room)) end
    for _, word in ipairs(ViewpointModelFix.STORAGE_WORDS) do
        if string.find(text, word, 1, true) then return "storage" end
    end
    return "store"
end

-- one of three arrangements, the same for a name every time
local function variant(name)
    local h = 0
    for i = 1, #name do h = (h * 31 + string.byte(name, i)) % 1000003 end
    return h % 3 + 1
end

local function overlayName(object)
    local overlay = object:getOverlaySprite()
    local name = overlay and overlay:getName()
    if name == "" then return nil end
    return name
end

-- The goods drawn over a stocked shelf are its overlay sprite; give it a goods model turned
-- like the shelf. An emptied shelf loses the overlay, and with it the goods.
local function checkGoods(object, square)
    local sprite = object:getSprite()
    local turn = sprite and goodsShelf[sprite:getName()]
    if not turn then return end
    local name = overlayName(object)
    if not name or checkedOverlay[name] then return end
    checkedOverlay[name] = true
    learn(name, string.format("goods_%s_%d,%d,0,0,0,1", goodsKind(name, square), variant(name), turn))
end

local function onSquare(square)
    local objects = square and square:getObjects()
    if not objects then return end
    for i = 0, objects:size() - 1 do
        local object = objects:get(i)
        check(object:getSprite())
        checkGoods(object, square)
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

-- Shift+F7: reload the models without restarting -------------------------------------------
--
-- Viewpoint keeps a model it has loaded for as long as the game runs, by file name, but
-- rebuilds every chunk when a pack is registered. So a reload copies each model to a new
-- name, writes a pack binding everything to the copies, and registers it. Changed OBJ files,
-- atlas.png and binds added to pack.txt all show at once; a new kind of model, or a change to
-- this Lua file, still needs a restart.

local reloads = 0

local function readModFile(path)
    local ok, reader = pcall(getModFileReader, MOD_ID, path, false)
    if not ok or not reader then return nil end
    local lines = {}
    local line = reader:readLine()
    while line do
        table.insert(lines, line)
        line = reader:readLine()
    end
    reader:close()
    return lines
end

local function writeModFile(path, lines)
    local writer = getModFileWriter(MOD_ID, path, true, false)
    if not writer then return false end
    for _, line in ipairs(lines) do writer:writeln(line) end
    writer:close()
    return true
end

function ViewpointModelFix.reload()
    local packs = viewpointPacks()
    local at = findWriteAt()
    if not packs or not at then
        log("reload: no folder to write into")
        return
    end
    reloads = reloads + 1
    local tag = string.format("r%d", reloads)

    local manifest = {
        "# written by ViewpointModelFix.lua (Shift+F7); rewritten every reload",
        "id=ViewpointModelFix-" .. tag,
        "name=Model fixes (reload " .. reloads .. ")",
    }
    local copied = 0
    for _, model in ipairs(MODELS) do
        local lines = readModFile(at.read .. model .. ".obj")
        if lines and writeModFile(at.dir .. model .. "." .. tag .. ".obj", lines) then
            table.insert(manifest, string.format("model.%s=%s.%s.obj", model, model, tag))
            copied = copied + 1
        else
            log("reload: could not copy " .. model .. ".obj")
        end
    end

    local binds = 0
    for name, value in pairs(learned) do
        table.insert(manifest, "bind." .. name .. "=" .. value)
        binds = binds + 1
    end
    -- binds added to pack.txt by hand
    for _, line in ipairs(readModFile(at.read .. "pack.txt") or {}) do
        if string.match(line, "^bind%.") then
            table.insert(manifest, line)
            binds = binds + 1
        end
    end

    local file = "reload_" .. reloads .. ".txt"
    if not writeModFile(at.dir .. file, manifest) then
        log("reload: could not write " .. file)
        return
    end
    local ok, result = pcall(packs.register, MOD_ID, "media/" .. PACK_DIR .. file)
    local text
    if ok and result then
        text = string.format("Models reloaded: %d models, %d objects", copied, binds)
    else
        text = "Model reload failed, see console.txt"
    end
    log(text .. " (" .. file .. ")")
    local player = getPlayer()
    if player then player:Say(text) end
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
                    local object = objects:get(i)
                    local sprite = object:getSprite()
                    local name = sprite and sprite:getName()
                    local overlay = overlayName(object)
                    if overlay and name and not seen["overlay " .. overlay] then
                        seen["overlay " .. overlay] = true
                        table.insert(lines, string.format("overlay:  %s on %s = %s", overlay, name,
                            learned[overlay] or "no model"))
                    end
                    if name and not seen[name] then
                        seen[name] = true
                        local info = describe(sprite)
                        local about = string.format("%s / %s, facing %s%s",
                            info.custom or "?", info.group or "?", info.facing or "?",
                            info.part and (", " .. info.part .. " of the bed") or "")
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
    if key ~= Keyboard.KEY_F7 then return end
    if isKeyDown(Keyboard.KEY_LSHIFT) or isKeyDown(Keyboard.KEY_RSHIFT) then
        ViewpointModelFix.reload()
    else
        ViewpointModelFix.dump()
    end
end

readLearned()
register()
Events.OnGameBoot.Add(register)
Events.LoadGridsquare.Add(safeOnSquare)
Events.OnGameStart.Add(onGameStart)
Events.EveryOneMinute.Add(flush)
Events.OnKeyPressed.Add(onKey)
