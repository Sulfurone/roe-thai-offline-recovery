-- Local diagnostic: names and types only, no game-state writes or network calls.
pcall(function()
    local output = "F:/roe/recovery/private/thai-preload-api.txt"
    if io and io.open then
        local file = io.open(output, "w")
        if file then
            file:write("ROE_THAI_PRELOAD_PROBE_V1\n")
            file:write("root\t" .. tostring(__ROOT_DIR__) .. "\n")
            for name, value in pairs(_G) do
                file:write("global\t" .. tostring(name) .. "\t" .. type(value) .. "\n")
            end
            if type(qs) == "table" then
                for name, value in pairs(qs) do
                    file:write("qs\t" .. tostring(name) .. "\t" .. type(value) .. "\n")
                end
            end
            file:close()
        end
    end
    if qs and qs.QSPrint then
        qs.QSPrint("ROE_THAI_PRELOAD_PROBE_V1")
    end
end)
