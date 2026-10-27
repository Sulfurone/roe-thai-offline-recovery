-- Temporary, read-only API inventory for this user's Thai restoration work.
-- No game state mutation, messages, network access, or original file changes.
do
    local target = "F:/roe/recovery/private/thai-lua-api.txt"
    if type(io) == "table" and type(io.open) == "function" then
        local stream = io.open(target, "w")
        if stream then
            stream:write("Thai client ScriptCustom diagnostic loaded\n")
            stream:write("root=" .. tostring(__ROOT_DIR__) .. "\n")
            stream:write("shipping=" .. tostring(__SHIPPING__) .. "\n")
            if type(qs) == "table" then
                local names = {}
                for name, value in pairs(qs) do
                    if type(name) == "string" then
                        names[#names + 1] = name .. "\t" .. type(value)
                    end
                end
                table.sort(names)
                for _, name in ipairs(names) do
                    stream:write(name .. "\n")
                end
            else
                stream:write("qs_type=" .. type(qs) .. "\n")
            end
            stream:close()
        end
    end
end
