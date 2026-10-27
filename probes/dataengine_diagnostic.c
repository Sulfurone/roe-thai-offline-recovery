/* One-run, local diagnostic. No hooks, process writes or remote-process APIs. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>

#define IMAGE_BYTES 50941952u
#define OUTPUT_DIR "F:\\roe\\recovery\\private\\runtime-diag-1\\"
static const char expected_client[] = "F:\\roe\\32838\\Europa_Client.exe";
static const char original_dll[] = "F:\\roe\\32838\\_ROE_Original_DataEngine.dll";
static unsigned char zeros[4096];

static void status(const char *message, DWORD error) {
    HANDLE file = CreateFileA(OUTPUT_DIR "status.bin", GENERIC_WRITE,
                             FILE_SHARE_READ, NULL, CREATE_ALWAYS,
                             FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    DWORD written;
    WriteFile(file, message, (DWORD)lstrlenA(message), &written, NULL);
    WriteFile(file, "\n", 1, &written, NULL);
    WriteFile(file, &error, 4, &written, NULL);
    CloseHandle(file);
}

static int readable(DWORD protect) {
    if (protect & PAGE_GUARD) return 0;
    switch (protect & 255) {
        case PAGE_READONLY: case PAGE_READWRITE: case PAGE_WRITECOPY:
        case PAGE_EXECUTE_READ: case PAGE_EXECUTE_READWRITE:
        case PAGE_EXECUTE_WRITECOPY: return 1;
        default: return 0;
    }
}

static DWORD WINAPI collect(void *parameter) {
    (void)parameter;
    char path[MAX_PATH];
    DWORD length = GetModuleFileNameA(NULL, path, MAX_PATH);
    if (!length || length >= MAX_PATH || lstrcmpiA(path, expected_client)) return 0;
    /* Preserve the original module's initialization and its two forwarded APIs. */
    if (!LoadLibraryA(original_dll)) {
        status("original_load_failed", GetLastError());
        return 0;
    }
    status("waiting_for_client_initialization", 0);
    Sleep(15000);
    unsigned char *base = (unsigned char *)GetModuleHandleA(NULL);
    if (!base) { status("no_main_module", GetLastError()); return 0; }
    HANDLE file = CreateFileA(OUTPUT_DIR "thai-self-image.bin", GENERIC_WRITE,
                             FILE_SHARE_READ, NULL, CREATE_NEW,
                             FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) {
        status("output_open_failed", GetLastError());
        return 0;
    }
    struct {
        char magic[8];
        uint32_t image_base;
        uint32_t image_size;
    } header = {{'R','O','E','T','H','A','I','1'}, (uint32_t)(uintptr_t)base, IMAGE_BYTES};
    _Static_assert(sizeof(header) == 16, "Unexpected header layout");
    _Static_assert(sizeof(void *) == 4, "Build this diagnostic for x86");
    DWORD written = 0, copied = 0, skipped = 0;
    if (!WriteFile(file, &header, sizeof(header), &written, NULL) || written != sizeof(header)) {
        DWORD error = GetLastError(); CloseHandle(file); status("header_write_failed", error); return 0;
    }
    for (DWORD offset = 0; offset < IMAGE_BYTES; offset += 4096) {
        MEMORY_BASIC_INFORMATION region;
        const void *source = zeros;
        DWORD count = IMAGE_BYTES - offset;
        if (count > 4096) count = 4096;
        if (VirtualQuery(base + offset, &region, sizeof(region)) == sizeof(region)
                && region.State == MEM_COMMIT && readable(region.Protect)) {
            source = base + offset;
            copied += count;
        } else {
            skipped += count;
        }
        /* Kernel file I/O probes the source; no page protections are changed. */
        written = 0;
        if (!WriteFile(file, source, count, &written, NULL) || written != count) {
            DWORD error = GetLastError(); CloseHandle(file); status("image_write_failed", error); return 0;
        }
    }
    FlushFileBuffers(file);
    CloseHandle(file);
    HANDLE counters = CreateFileA(OUTPUT_DIR "counts.bin", GENERIC_WRITE,
                                 FILE_SHARE_READ, NULL, CREATE_NEW,
                                 FILE_ATTRIBUTE_NORMAL, NULL);
    if (counters != INVALID_HANDLE_VALUE) {
        WriteFile(counters, &copied, 4, &written, NULL);
        WriteFile(counters, &skipped, 4, &written, NULL);
        CloseHandle(counters);
    }
    status("snapshot_complete", 0);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, LPVOID reserved) {
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(module);
        HANDLE thread = CreateThread(NULL, 0, collect, NULL, 0, NULL);
        if (thread) CloseHandle(thread);
    }
    return TRUE;
}
