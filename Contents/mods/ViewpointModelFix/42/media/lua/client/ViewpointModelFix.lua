-- Registers this mod's model pack with Viewpoint, and adds a helper (F7) that lists the
-- sprites round the player as ready-to-paste bind lines for pack.txt.

ViewpointModelFix = ViewpointModelFix or {}

local MOD_ID = "ViewpointModelFix"
local MANIFEST = "media/viewpoint/ViewpointModelFix/pack.txt"
local DUMP_FILE = "ViewpointModelFix_binds.txt"
local DUMP_RADIUS = 3

-- Turn per sprite facing, in degrees. The models face south with their back to a north wall.
-- If they all come out backwards or sideways in game, this table is the one place to fix it.
ViewpointModelFix.DEGREES = { S = 0, W = 90, N = 180, E = 270 }

-- Which model a sprite gets, matched against its CustomName / GroupName (lower case).
ViewpointModelFix.MATCHES = {
    { "urinal", "urinal" },
    { "toilet", "toilet" },
    { "sink", "sink" },
    { "metal shel", "shelf_metal" },
    { "shelves", "shelf_metal" },
    { "cardboard", "box_small" },
}

local registered = false

local function register()
    if registered then return end
    local packs = Viewpoint and Viewpoint.ModelPacks
    if not packs or not packs.register then return end
    local ok, result = pcall(packs.register, MOD_ID, MANIFEST)
    if ok and result then
        registered = true
        print("[ViewpointModelFix] model pack registered")
    elseif not ok then
        print("[ViewpointModelFix] registering the model pack failed: " .. tostring(result))
    end
end

ViewpointModelFix.register = register

local function prop(props, key)
    if not props then return nil end
    for _, getter in ipairs({ "Val", "get" }) do
        local ok, value = pcall(function() return props[getter](props, key) end)
        if ok and value ~= nil and value ~= "" then return tostring(value) end
    end
    return nil
end

local function modelFor(custom, group)
    local text = string.lower((custom or "") .. " " .. (group or ""))
    for _, match in ipairs(ViewpointModelFix.MATCHES) do
        if string.find(text, match[1], 1, true) then return match[2] end
    end
    return nil
end

local function bindLine(name, custom, group, facing)
    local model = modelFor(custom, group)
    local degrees = ViewpointModelFix.DEGREES[facing or "S"] or 0
    local about = string.format("%s / %s, facing %s", custom or "?", group or "?", facing or "?")
    if model then
        return string.format("bind.%s=%s,%d,0,0,0,1   # %s", name, model, degrees, about), true
    end
    return string.format("# no model yet: %s   (%s)", name, about), false
end

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
                        local props = sprite:getProperties()
                        local line, ok = bindLine(name, prop(props, "CustomName"), prop(props, "GroupName"),
                            prop(props, "Facing"))
                        if ok then bound = bound + 1 end
                        table.insert(lines, line)
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
        print("[ViewpointModelFix] " .. line)
    end
    writer:close()

    player:Say(string.format("%d sprites, %d with a model: Zomboid/Lua/%s", #lines, bound, DUMP_FILE))
end

local function onKey(key)
    if key == Keyboard.KEY_F7 then ViewpointModelFix.dump() end
end

register()
Events.OnGameBoot.Add(register)
Events.OnGameStart.Add(register)
Events.OnKeyPressed.Add(onKey)
