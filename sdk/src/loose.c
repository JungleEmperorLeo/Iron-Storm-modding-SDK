/* ISModLoader.dll (front): loose-file support, then loads ISModLoader_core.dll (the full mod loader: console, plugins,
   level redirects, per-level arms) from the same folder. */
#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
static char gamedir[MAX_PATH];
static void ilog(const char *fmt, ...) {
    char path[MAX_PATH]; snprintf(path, sizeof path, "%sismod.log", gamedir);
    FILE *f = fopen(path, "a"); if (!f) return;
    va_list ap; va_start(ap, fmt); vfprintf(f, fmt, ap); va_end(ap); fputc('\n', f); fclose(f);
}
/* ---- loose files: every model/level file the game opens from a bigfile goes through BIGFILE::Open(name) (0x4c23d0),
   which seeks to the file inside the .ibf and loads it with a storage object. If a loose copy exists in one of the
   override folders, it is loaded from disk instead (same storage path, but through a file stream opened on the loose
   file). Folders: each line of ismod_override.txt (written by the launcher for the running mod), then <game>\override\.
   Files that are not in the bigfile at all also work, so mods can add new models. ---- */
#define BIGFILE_OPEN 0x4c23d0
#define FNX_MANAGER  0x5a0fa0
typedef void *(__thiscall *create_fn)(void *self, unsigned tag);
typedef int   (__thiscall *open_name_fn)(void *self, const char *path);
typedef int   (__thiscall *stor_open_fn)(void *self, void *load);
typedef unsigned (__thiscall *stor_id_fn)(void *self);
typedef int   (__thiscall *stor_read_fn)(void *self, void *obj);
static unsigned char *bf_tramp, *bf2_tramp, *bf3_tramp, *bf4_tramp; static int log_names;
static char ovr_dirs[16][MAX_PATH]; static int novr;
static int is_wav(const char *n) { size_t l = n ? strlen(n) : 0; return l > 4 && !_stricmp(n + l - 4, ".wav"); }
static int find_loose(const char *name, char *out) {
    const char *b = strrchr(name, '\\'); if (!b) b = strrchr(name, '/'); b = b ? b + 1 : name;
    for (int i = 0; i < novr; i++) {
        snprintf(out, MAX_PATH, "%s%s", ovr_dirs[i], b);
        if (GetFileAttributesA(out) != INVALID_FILE_ATTRIBUTES) return 1;
    }
    return 0;
}
#define VT(o, off) (*(void ***)(o))[(off) / 4]
static void *__fastcall hook_bigfile_open(void *self, void *edx, const char *name) {
    char path[MAX_PATH];
    if (name && (log_names || is_wav(name))) ilog("open %s", name);
    if (name && find_loose(name, path)) {
        void *mgr = *(void **)FNX_MANAGER, *stor = *(void **)self;
        void *fill = ((create_fn)VT(mgr, 0x1c))(mgr, 0x4c4c4946);            /* 'FILL' file stream */
        if (fill && stor && ((open_name_fn)VT(fill, 0x38))(fill, path) == 0) {
            ((stor_open_fn)VT(stor, 0x38))(stor, fill);
            unsigned id = ((stor_id_fn)VT(stor, 0x40))(stor);
            void *obj = ((create_fn)VT(mgr, 0x1c))(mgr, id);
            if (obj) { ((stor_read_fn)VT(stor, 0x6c))(stor, obj); ilog("loose file: %s", path); return obj; }
        }
        ilog("loose file %s could not be opened, using the bigfile", path);
    }
    return ((void *(__fastcall *)(void *, void *, const char *))bf_tramp)(self, edx, name);
}

/* BIGFILE::Load_Into(name, object) (0x4c2640): the other way the game reads a bigfile file, straight into an existing
   object (obj->vtable[0x1a4](storage)). Returns 0 on success, 1 when the file is not in the bigfile. */
typedef void (__thiscall *obj_load_fn)(void *self, void *stor);
static int __fastcall hook_bigfile_load(void *self, void *edx, const char *name, void *obj) {
    char path[MAX_PATH];
    if (name && (log_names || is_wav(name))) ilog("load %s", name);
    if (name && obj && find_loose(name, path)) {
        void *mgr = *(void **)FNX_MANAGER, *stor = *(void **)self;
        void *fill = ((create_fn)VT(mgr, 0x1c))(mgr, 0x4c4c4946);
        if (fill && stor && ((open_name_fn)VT(fill, 0x38))(fill, path) == 0) {
            ((stor_open_fn)VT(stor, 0x38))(stor, fill);
            ((obj_load_fn)VT(obj, 0x1a4))(obj, stor);
            ilog("loose file: %s", path); return 0;
        }
        ilog("loose file %s could not be opened, using the bigfile", path);
    }
    return ((int (__fastcall *)(void *, void *, const char *, void *))bf2_tramp)(self, edx, name, obj);
}
/* BIGFILE::Read_Alloc(name, char **out) (0x4c24b0) and BIGFILE::Size(name) (0x4c25a0): raw file data (sounds, text).
   Read_Alloc allocates size+1 bytes with the game's allocator, reads the file, adds a 0 and returns 0. */
static int loose_size(const char *path) {
    WIN32_FILE_ATTRIBUTE_DATA a; return GetFileAttributesExA(path, GetFileExInfoStandard, &a) ? (int)a.nFileSizeLow : -1;
}
static int __fastcall hook_bigfile_read(void *self, void *edx, const char *name, char **out) {
    char path[MAX_PATH];
    if (name && (log_names || is_wav(name))) ilog("read %s", name);
    if (name && out && find_loose(name, path)) {
        int n = loose_size(path); FILE *f = n >= 0 ? fopen(path, "rb") : NULL;
        if (f) {
            char *buf = ((char *(__cdecl *)(unsigned))0x528878)((unsigned)n + 1);
            size_t got = fread(buf, 1, (size_t)n, f); fclose(f); buf[got] = 0; *out = buf;
            ilog("loose file: %s", path); return 0;
        }
        ilog("loose file %s could not be opened, using the bigfile", path);
    }
    return ((int (__fastcall *)(void *, void *, const char *, char **))bf3_tramp)(self, edx, name, out);
}
static int __fastcall hook_bigfile_size(void *self, void *edx, const char *name) {
    char path[MAX_PATH];
    if (name && (log_names || is_wav(name))) ilog("size %s", name);
    if (name && find_loose(name, path)) { int n = loose_size(path); if (n >= 0) return n; }
    return ((int (__fastcall *)(void *, void *, const char *))bf4_tramp)(self, edx, name);
}
static unsigned char *hook_at(unsigned addr, void *fn) {
    unsigned char *p = (unsigned char *)addr;
    static const unsigned char pro[8] = {0x83, 0xec, 0x4c, 0xa1, 0x20, 0xcc, 0x59, 0x00};
    if (memcmp(p, pro, 8)) { ilog("bigfile code at %x not as expected", addr); return NULL; }
    unsigned char *t = VirtualAlloc(NULL, 16, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    memcpy(t, pro, 8); t[8] = 0xe9; *(int *)(t + 9) = (int)(p + 8) - (int)(t + 13);
    DWORD old; VirtualProtect(p, 8, PAGE_EXECUTE_READWRITE, &old);
    p[0] = 0xe9; *(int *)(p + 1) = (int)(unsigned char *)fn - (int)(p + 5); p[5] = p[6] = p[7] = 0x90;
    VirtualProtect(p, 8, old, &old); FlushInstructionCache(GetCurrentProcess(), p, 8);
    return t;
}
static void install_loose_files(void) {
    char list[MAX_PATH], line[MAX_PATH];
    snprintf(list, sizeof list, "%sismod_override.txt", gamedir);
    FILE *f = fopen(list, "r");
    while (f && fgets(line, sizeof line, f) && novr < 15) {
        line[strcspn(line, "\r\n")] = 0; if (!line[0]) continue;
        size_t n = strlen(line); if (line[n - 1] != '\\' && line[n - 1] != '/') strcat(line, "\\");
        if (line[1] == ':' || line[0] == '\\') strcpy(ovr_dirs[novr], line); else snprintf(ovr_dirs[novr], MAX_PATH, "%s%s", gamedir, line);
        novr++;
    }
    if (f) fclose(f);
    else {      /* no mod running: TrenchBroom test runs read the map's own sounds folder (written by map2is) */
        snprintf(list, sizeof list, "%sismod_test_sounds.txt", gamedir);
        if ((f = fopen(list, "r"))) {
            if (fgets(line, sizeof line, f) && novr < 15) {
                line[strcspn(line, "\r\n")] = 0; size_t n = strlen(line);
                if (n) { if (line[n - 1] != '\\') strcat(line, "\\"); strcpy(ovr_dirs[novr++], line); }
            }
            fclose(f);
        }
    }
    snprintf(ovr_dirs[novr++], MAX_PATH, "%soverride\\", gamedir);
    { char t[MAX_PATH]; snprintf(t, sizeof t, "%soverride\\log_names.txt", gamedir); log_names = GetFileAttributesA(t) != INVALID_FILE_ATTRIBUTES; }
    bf_tramp = hook_at(BIGFILE_OPEN, (void *)hook_bigfile_open);
    bf2_tramp = hook_at(0x4c2640, (void *)hook_bigfile_load);
    bf3_tramp = hook_at(0x4c24b0, (void *)hook_bigfile_read);
    bf4_tramp = hook_at(0x4c25a0, (void *)hook_bigfile_size);
    for (int i = 0; i < novr; i++) ilog("loose files from %s", ovr_dirs[i]);
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        GetModuleFileNameA(NULL, gamedir, MAX_PATH);
        char *s = strrchr(gamedir, '\\'); if (s) s[1] = 0;
        install_loose_files();
        char core[MAX_PATH]; GetModuleFileNameA(h, core, MAX_PATH);
        s = strrchr(core, '\\'); strcpy(s ? s + 1 : core, "ISModLoader_core.dll");
        if (!LoadLibraryA(core)) {
            snprintf(core, sizeof core, "%sISModLoader_core.dll", gamedir);
            if (!LoadLibraryA(core)) ilog("cannot load ISModLoader_core.dll (error %lu)", GetLastError());
        }
    }
    return TRUE;
}
