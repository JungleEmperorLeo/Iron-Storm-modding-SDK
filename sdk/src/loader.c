/* ISModLoader.dll: loaded by the patched game (ISModGame.exe) at the main menu. Loads the plugin DLLs listed in
   ismod_plugins.txt (written by the launcher) and gives them the ISModAPI. */
#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include "ismod.h"

#define REGISTER_NATIVE 0x520ae0      /* int cdecl (void *script, const char *name, void *fn) */
#define GET_STRING_ARG  0x520c40      /* int cdecl (int arg, char *out) */
#define GET_INT_ARG     0x520c90      /* int cdecl (int arg, int *out) */
#define GET_FLOAT_ARG   0x520d30      /* int cdecl (int arg, float *out) */
#define WORLD           0x59ee58      /* game world pointer */

typedef int (__cdecl *reg_fn)(void *, const char *, void *);
static reg_fn orig_register;
static struct { char name[64]; ISModCommand fn; } cmds[256];
static int ncmds;
static void *last_script;
static char gamedir[MAX_PATH];

static void ilog(const char *fmt, ...) {
    char path[MAX_PATH]; snprintf(path, sizeof path, "%sismod.log", gamedir);
    FILE *f = fopen(path, "a"); if (!f) return;
    va_list ap; va_start(ap, fmt); vfprintf(f, fmt, ap); va_end(ap); fputc('\n', f); fclose(f);
}
static void api_register(const char *name, ISModCommand fn) {
    if (ncmds < 256) { strncpy(cmds[ncmds].name, name, 63); cmds[ncmds].fn = fn; ncmds++; ilog("command %s", name); }
}
static int api_get_int(int a) { int v = 0; ((int (__cdecl *)(int, int *))GET_INT_ARG)(a, &v); return v; }
static float api_get_float(int a) { float v = 0; ((int (__cdecl *)(int, float *))GET_FLOAT_ARG)(a, &v); return v; }
static const char *api_get_string(int a) { static char buf[1024]; buf[0] = 0; ((int (__cdecl *)(int, char *))GET_STRING_ARG)(a, buf); return buf; }
static void *api_character(int id) {
    char *w = *(char **)WORLD; if (!w || (id >> 16) != 0x000a) return NULL;     /* 0x000a = character ids */
    char *t = *(char **)(*(char **)(*(char **)(w + 0x660) + 0xc) + 0x28);
    return t ? *(void **)(t + (id & 0xffff) * 4) : NULL;
}
static float *api_health(int id) { char *c = api_character(id); return c ? (float *)(c + 0x154) : NULL; }

static const ISModAPI api = { ISMOD_API_VERSION, api_register, api_get_int, api_get_float, api_get_string,
                              api_character, api_health, ilog };

/* hook: the game binds its native commands to each loaded level script; we add the plugin commands too */
static int __cdecl hook_register(void *script, const char *name, void *fn) {
    int r = orig_register(script, name, fn);
    if (script && script != last_script) {
        last_script = script;
        for (int i = 0; i < ncmds; i++) orig_register(script, cmds[i].name, (void *)cmds[i].fn);
    }
    return r;
}
static void install_hook(void) {
    unsigned char *p = (unsigned char *)REGISTER_NATIVE;
    static const unsigned char expect[5] = {0x51, 0x8b, 0x44, 0x24, 0x08};
    if (memcmp(p, expect, 5)) { ilog("unexpected bytes at register_native: not Game.exe 1.041?"); return; }
    unsigned char *t = VirtualAlloc(NULL, 16, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    memcpy(t, p, 5); t[5] = 0xe9; *(int *)(t + 6) = (int)(p + 5) - (int)(t + 10);
    orig_register = (reg_fn)t;
    DWORD old; VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &old);
    p[0] = 0xe9; *(int *)(p + 1) = (int)(unsigned char *)hook_register - (int)(p + 5);
    VirtualProtect(p, 5, old, &old); FlushInstructionCache(GetCurrentProcess(), p, 5);
}
static void load_plugins(void) {
    char list[MAX_PATH], line[MAX_PATH];
    snprintf(list, sizeof list, "%sismod_plugins.txt", gamedir);
    FILE *f = fopen(list, "r"); if (!f) { ilog("no ismod_plugins.txt"); return; }
    while (fgets(line, sizeof line, f)) {
        line[strcspn(line, "\r\n")] = 0; if (!line[0]) continue;
        HMODULE m = LoadLibraryA(line);
        if (!m) { ilog("cannot load %s (error %lu)", line, GetLastError()); continue; }
        void (__cdecl *init)(const ISModAPI *) = (void (__cdecl *)(const ISModAPI *))GetProcAddress(m, "ISMod_Init");
        if (!init) { ilog("%s has no ISMod_Init", line); continue; }
        ilog("loaded %s", line); init(&api);
    }
    fclose(f);
}

/* ---- level redirection: ismod_paths.txt lines  "test=<path>"  or  "campaign N=<path>"  (path without extension, e.g.
   Mods\\x\\lv2\\level\\lv2 ; relative to the game folder, or absolute). The game builds "levels\campaign\levelN\lvN" with
   sprintf and the Test slot from a fixed string; both are redirected here, so the level files can stay in the mod. */
#define SPRINTF_IAT 0x532180
#define FMT_CAMPAIGN 0x53363c
static struct { int n; char path[260]; } redir[64];
static int nredir;
static char test_path[256];
static char test_buf[256] = "levels\\multi\\test\\test";   /* what the Test slot loads (redirected / console "map") */
typedef int (__cdecl *sprintf_fn)(char *, const char *, ...);
static int __cdecl hook_sprintf(char *buf, const char *fmt, ...) {
    va_list ap; va_start(ap, fmt); int r = vsprintf(buf, fmt, ap); va_end(ap);
    if (fmt == (const char *)FMT_CAMPAIGN) {
        int n = 0; sscanf(buf, "levels\\campaign\\level%d", &n);
        for (int i = 0; i < nredir; i++) if (redir[i].n == n) {
            strcpy(buf, redir[i].path); ilog("level %d -> %s", n, buf); return (int)strlen(buf);
        }
    }
    return r;
}
static void install_redirects(void) {
    char list[MAX_PATH], line[400];
    snprintf(list, sizeof list, "%sismod_paths.txt", gamedir);
    FILE *f = fopen(list, "r");
    while (f && fgets(line, sizeof line, f)) {
        line[strcspn(line, "\r\n")] = 0; char *eq = strchr(line, '='); if (!eq) continue; *eq = 0;
        if (!strcmp(line, "test")) { strncpy(test_path, eq + 1, 255); }
        else { int n; if (sscanf(line, "campaign %d", &n) == 1 && nredir < 64) { redir[nredir].n = n; strncpy(redir[nredir].path, eq + 1, 259); nredir++; } }
    }
    if (f) fclose(f);
    snprintf(list, sizeof list, "%sismod_next.txt", gamedir);
    if ((f = fopen(list, "r"))) { if (fgets(line, sizeof line, f)) { line[strcspn(line, "\r\n")] = 0; strncpy(test_path, line, 255); } fclose(f); DeleteFileA(list); }
    DWORD old;
    if (nredir) {
        unsigned *iat = (unsigned *)SPRINTF_IAT;
        VirtualProtect(iat, 4, PAGE_READWRITE, &old); *iat = (unsigned)hook_sprintf; VirtualProtect(iat, 4, old, &old);
        ilog("campaign redirects: %d", nredir);
    }
    {        /* code at 0x473575: mov ecx,5 ; mov esi,<"levels\multi\test\test"> ; ... rep movsd */
        unsigned char *c = (unsigned char *)0x473575;
        if (c[0] == 0xb9 && c[5] == 0xbe && *(unsigned *)(c + 6) == 0x538a38) {
            char *buf = test_buf; if (test_path[0]) { memset(buf, 0, 256); strncpy(buf, test_path, 255); }
            VirtualProtect(c, 12, PAGE_EXECUTE_READWRITE, &old);
            *(unsigned *)(c + 1) = 40; *(unsigned *)(c + 6) = (unsigned)buf;
            VirtualProtect(c, 12, old, &old); FlushInstructionCache(GetCurrentProcess(), c, 12);
            ilog("test slot -> %s", test_buf);
        } else ilog("test slot code not as expected");
    }
}


static const unsigned char font5x7[95][5] = {
{0,0,0,0,0},{0,0,0x5F,0,0},{0,7,0,7,0},{0x14,0x7F,0x14,0x7F,0x14},{0x24,0x2A,0x7F,0x2A,0x12},{0x23,0x13,8,0x64,0x62},{0x36,0x49,0x56,0x20,0x50},{0,5,3,0,0},
{0,0x1C,0x22,0x41,0},{0,0x41,0x22,0x1C,0},{0x2A,0x1C,0x7F,0x1C,0x2A},{8,8,0x3E,8,8},{0,0x50,0x30,0,0},{8,8,8,8,8},{0,0x60,0x60,0,0},{0x20,0x10,8,4,2},
{0x3E,0x51,0x49,0x45,0x3E},{0,0x42,0x7F,0x40,0},{0x42,0x61,0x51,0x49,0x46},{0x21,0x41,0x45,0x4B,0x31},{0x18,0x14,0x12,0x7F,0x10},{0x27,0x45,0x45,0x45,0x39},{0x3C,0x4A,0x49,0x49,0x30},{1,0x71,9,5,3},
{0x36,0x49,0x49,0x49,0x36},{6,0x49,0x49,0x29,0x1E},{0,0x36,0x36,0,0},{0,0x56,0x36,0,0},{8,0x14,0x22,0x41,0},{0x14,0x14,0x14,0x14,0x14},{0,0x41,0x22,0x14,8},{2,1,0x51,9,6},
{0x32,0x49,0x79,0x41,0x3E},{0x7E,0x11,0x11,0x11,0x7E},{0x7F,0x49,0x49,0x49,0x36},{0x3E,0x41,0x41,0x41,0x22},{0x7F,0x41,0x41,0x22,0x1C},{0x7F,0x49,0x49,0x49,0x41},{0x7F,9,9,9,1},{0x3E,0x41,0x49,0x49,0x7A},
{0x7F,8,8,8,0x7F},{0,0x41,0x7F,0x41,0},{0x20,0x40,0x41,0x3F,1},{0x7F,8,0x14,0x22,0x41},{0x7F,0x40,0x40,0x40,0x40},{0x7F,2,0x0C,2,0x7F},{0x7F,4,8,0x10,0x7F},{0x3E,0x41,0x41,0x41,0x3E},
{0x7F,9,9,9,6},{0x3E,0x41,0x51,0x21,0x5E},{0x7F,9,0x19,0x29,0x46},{0x46,0x49,0x49,0x49,0x31},{1,1,0x7F,1,1},{0x3F,0x40,0x40,0x40,0x3F},{0x1F,0x20,0x40,0x20,0x1F},{0x3F,0x40,0x38,0x40,0x3F},
{0x63,0x14,8,0x14,0x63},{7,8,0x70,8,7},{0x61,0x51,0x49,0x45,0x43},{0,0x7F,0x41,0x41,0},{2,4,8,0x10,0x20},{0,0x41,0x41,0x7F,0},{4,2,1,2,4},{0x40,0x40,0x40,0x40,0x40},
{0,1,2,4,0},{0x20,0x54,0x54,0x54,0x78},{0x7F,0x48,0x44,0x44,0x38},{0x38,0x44,0x44,0x44,0x20},{0x38,0x44,0x44,0x48,0x7F},{0x38,0x54,0x54,0x54,0x18},{8,0x7E,9,1,2},{0x0C,0x52,0x52,0x52,0x3E},
{0x7F,8,4,4,0x78},{0,0x44,0x7D,0x40,0},{0x20,0x40,0x44,0x3D,0},{0x7F,0x10,0x28,0x44,0},{0,0x41,0x7F,0x40,0},{0x7C,4,0x18,4,0x78},{0x7C,8,4,4,0x78},{0x38,0x44,0x44,0x44,0x38},
{0x7C,0x14,0x14,0x14,8},{8,0x14,0x14,0x18,0x7C},{0x7C,8,4,4,8},{0x48,0x54,0x54,0x54,0x20},{4,0x3F,0x44,0x40,0x20},{0x3C,0x40,0x40,0x20,0x7C},{0x1C,0x20,0x40,0x20,0x1C},{0x3C,0x40,0x30,0x40,0x3C},
{0x44,0x28,0x10,0x28,0x44},{0x0C,0x50,0x50,0x50,0x3C},{0x44,0x64,0x54,0x4C,0x44},{0,8,0x36,0x41,0},{0,0,0x7F,0,0},{0,0x41,0x36,8,0},{0x10,8,8,0x10,8}
};

/* ---- Quake-style console: press ` in the game. A translucent panel drops over the top half of the screen (drawn by hooking
   Direct3D 8 EndScene); typing goes to a small invisible window that takes the keyboard focus, so the game stops reacting
   to keys while the console is open. Enter runs a command; Up/Down = history; PgUp/PgDn = scroll; ` or Esc closes. ---- */
#include <d3d8.h>
#define DIRECTINPUT_VERSION 0x0800
#include <dinput.h>
#define CON_MAX 200
static char con_text[CON_MAX][160]; static int con_n, con_scroll;
static char con_in[160]; static int con_len;
static char hist[32][160]; static int nhist, hpos;
static volatile int con_open;
static volatile int pending_map, pending_set, esc_step, hide_menu_req, pending_restart;
typedef void (__thiscall *loadlevel_fn)(void *, int, int);
#define LOAD_LEVEL 0x473520
#define SET_PAGE 0x471fa0
typedef void (__thiscall *setpage_fn)(void *, int);
#define GUI_OBJ 0x59ce40
static HWND game_wnd;
static void con_print(const char *fmt, ...) {
    char b[160]; va_list ap; va_start(ap, fmt); vsnprintf(b, sizeof b, fmt, ap); va_end(ap);
    if (con_n == CON_MAX) { memmove(con_text[0], con_text[1], sizeof con_text - sizeof con_text[0]); con_n--; }
    strcpy(con_text[con_n++], b);
}
static volatile int mp_active;
/* IS_FNX_APP::Start_Game (Game.exe 0x403830, thiscall): its first stack argument is the game mode; 2..5 (dm, tdm, ctf, cic)
   create the network game. A small stub records that before running the original prologue. */
static void install_mp_hook(void) {
    static const unsigned char pro[5] = {0x55, 0x8b, 0xec, 0x6a, 0xff}; DWORD old;
    unsigned char *f = (unsigned char *)0x403830;
    if (memcmp(f, pro, 5)) { ilog("Start_Game not as expected"); return; }
    unsigned char *t = VirtualAlloc(NULL, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE), *p = t;
    *p++ = 0x8b; *p++ = 0x44; *p++ = 0x24; *p++ = 0x04;                       /* mov eax,[esp+4] */
    *p++ = 0x83; *p++ = 0xe8; *p++ = 0x02;                                     /* sub eax,2 */
    *p++ = 0x83; *p++ = 0xf8; *p++ = 0x03;                                     /* cmp eax,3 */
    *p++ = 0x0f; *p++ = 0x96; *p++ = 0xc0;                                     /* setbe al */
    *p++ = 0x0f; *p++ = 0xb6; *p++ = 0xc0;                                     /* movzx eax,al */
    *p++ = 0xa3; *(unsigned *)p = (unsigned)&mp_active; p += 4;                /* mov [mp_active],eax */
    memcpy(p, pro, 5); p += 5;                                                 /* original prologue */
    *p = 0xe9; *(int *)(p + 1) = (int)(f + 5) - (int)(p + 5);                  /* jmp 0x403835 */
    VirtualProtect(f, 5, PAGE_EXECUTE_READWRITE, &old);
    f[0] = 0xe9; *(int *)(f + 1) = (int)t - (int)(f + 5);
    VirtualProtect(f, 5, old, &old); FlushInstructionCache(GetCurrentProcess(), f, 5);
    ilog("multiplayer detection ready");
}
static int console_allowed(void) { return !(mp_active && *(void **)0x59ee4c); }
static void con_run(char *line) {
    char cmd[64] = ""; float v = 0; int has = 0; char *arg = line;
    sscanf(line, "%63s", cmd); arg = line + strlen(cmd); while (*arg == ' ') arg++;
    has = sscanf(arg, "%f", &v) == 1;
    ilog("console: %s", line);
    if (!cmd[0]) return;
    if (!console_allowed()) { con_print("console commands are disabled in multiplayer"); return; }
    if (!_stricmp(cmd, "help")) { con_print("commands: health <n>, god, kill, list, clear, hidemenu, restart, quit, help");
        con_print("  map <n>       campaign level n (1-15)");
        con_print("  map test      the Test slot");
        con_print("  map <path>    any level: a folder or .gex file, relative to the game folder or absolute"); }
    else if (!_stricmp(cmd, "map")) {
        char a[200]; if (sscanf(arg, "%199[^\r\n]", a) != 1) { con_print("usage: map <n> | test | <path>"); return; }
        int n = 0, num = sscanf(a, "%d", &n) == 1 && strspn(a, "0123456789") == strlen(a);
        if (!num) {
            if (_stricmp(a, "test")) {
                char p[256]; strncpy(p, a, 200); p[200] = 0; size_t L = strlen(p);
                while (L && (p[L-1] == '\\' || p[L-1] == '/')) p[--L] = 0;
                if (L > 4 && !_stricmp(p + L - 4, ".gex")) p[L - 4] = 0;
                else { char g[300]; const char *b = strrchr(p, '\\'); const char *b2 = strrchr(p, '/'); if (b2 > b) b = b2; b = b ? b + 1 : p;
                       snprintf(g, sizeof g, "%s\\%s.gex", p, b);
                       char full[400]; snprintf(full, sizeof full, "%s%s", p[1] == ':' ? "" : gamedir, g);
                       if (GetFileAttributesA(full) != INVALID_FILE_ATTRIBUTES) { strcat(p, "\\"); strcat(p, b); } }
                char chk[400]; snprintf(chk, sizeof chk, "%s%s.gex", p[1] == ':' ? "" : gamedir, p);
                if (GetFileAttributesA(chk) == INVALID_FILE_ATTRIBUTES) { con_print("no level at %s", chk); return; }
                memset(test_buf, 0, sizeof test_buf); strncpy(test_buf, p, 255);
            }
            n = 0;
        }
        pending_map = n; pending_set = 1; con_open = 0;
        con_print("loading %s", n ? a : test_buf);
    }
    else if (!_stricmp(cmd, "clear")) con_n = 0;
    else if (!_stricmp(cmd, "hidemenu")) hide_menu_req = 1;
    else if (!_stricmp(cmd, "restart")) { pending_restart = 1; }
    else if (!_stricmp(cmd, "quit") || !_stricmp(cmd, "exit")) { ilog("console: quit"); ExitProcess(0); }
    else if (!_stricmp(cmd, "health") || !_stricmp(cmd, "god")) {
        float *h = api_health(0x000a0000); if (!h) { con_print("no player"); return; }
        *h = !_stricmp(cmd, "god") ? 99999.0f : (has ? v : *h); con_print("player health = %.0f", *h);
    } else if (!_stricmp(cmd, "kill")) {
        float *h = api_health(0x000a0000); if (h) { *h = 0.0f; con_print("player health = 0"); } else con_print("no player");
    } else if (!_stricmp(cmd, "list")) {
        for (int i = 0; i < 64; i++) { float *h = api_health(0x000a0000 + i); if (h) con_print("%08x health %.0f", 0x000a0000 + i, *h); }
    } else con_print("unknown command: %s (try help)", cmd);
}
static void con_key(DWORD vk, DWORD scan) {
    if (vk == VK_ESCAPE || vk == VK_OEM_3) { con_open = 0; return; }
    if (vk == VK_RETURN) { if (con_len) { con_in[con_len] = 0; con_print("> %s", con_in); con_run(con_in);
            if (nhist < 32) strcpy(hist[nhist++], con_in); else { memmove(hist[0], hist[1], sizeof hist - sizeof hist[0]); strcpy(hist[31], con_in); }
            hpos = nhist; con_len = 0; con_scroll = 0; } return; }
    if (vk == VK_BACK) { if (con_len) con_len--; return; }
    if (vk == VK_UP) { if (hpos > 0) { hpos--; strcpy(con_in, hist[hpos]); con_len = (int)strlen(con_in); } return; }
    if (vk == VK_DOWN) { if (hpos < nhist - 1) { hpos++; strcpy(con_in, hist[hpos]); con_len = (int)strlen(con_in); } else { hpos = nhist; con_len = 0; } return; }
    if (vk == VK_PRIOR) { if (con_scroll < con_n) con_scroll += 5; return; }
    if (vk == VK_NEXT) { con_scroll -= 5; if (con_scroll < 0) con_scroll = 0; return; }
    BYTE ks[256] = {0};
    if (GetAsyncKeyState(VK_SHIFT) & 0x8000) ks[VK_SHIFT] = 0x80;
    if (GetKeyState(VK_CAPITAL) & 1) ks[VK_CAPITAL] = 1;
    WORD ch = 0;
    if (ToAscii(vk, scan, ks, &ch, 0) == 1 && ch >= 32 && ch < 127 && ch != '`' && ch != '~' && con_len < 150) con_in[con_len++] = (char)ch;
}
/* The game reads the keyboard through DirectInput 8, so keys never reach normal Windows hooks. We hook the DirectInput device
   methods (shared by every device, found with a throw-away keyboard device): the console sees each key press, and while it
   is open the game gets an empty keyboard. */
typedef HRESULT (WINAPI *getstate_fn)(IDirectInputDevice8A *, DWORD, LPVOID);
typedef HRESULT (WINAPI *getdata_fn)(IDirectInputDevice8A *, DWORD, LPDIDEVICEOBJECTDATA, LPDWORD, DWORD);
static getstate_fn orig_state; static getdata_fn orig_data;
static void *kb_devs[8]; static void *other_devs[16]; static int nkb, nother;
static int is_keyboard(IDirectInputDevice8A *d) {
    for (int i = 0; i < nkb; i++) if (kb_devs[i] == d) return 1;
    for (int i = 0; i < nother; i++) if (other_devs[i] == d) return 0;
    DIDEVICEINSTANCEA di; memset(&di, 0, sizeof di); di.dwSize = sizeof di;
    int kb = SUCCEEDED(IDirectInputDevice8_GetDeviceInfo(d, &di)) && (di.dwDevType & 0xff) == DI8DEVTYPE_KEYBOARD;
    if (kb && nkb < 8) kb_devs[nkb++] = d; else if (!kb && nother < 16) other_devs[nother++] = d;
    ilog("console: input device %p keyboard=%d", (void *)d, kb);
    return kb;
}
static void key_event(DWORD dik, int down) {
    if (!down) return;
    if (dik == DIK_GRAVE) { con_open = !con_open; if (con_open) { con_len = 0; ilog("console: opened"); } return; }
    if (!con_open) return;
    UINT vk = MapVirtualKeyA(dik & 0x7f, 1 /* MAPVK_VSC_TO_VK */);
    switch (dik) { case DIK_UP: vk = VK_UP; break; case DIK_DOWN: vk = VK_DOWN; break; case DIK_PRIOR: vk = VK_PRIOR; break;
                   case DIK_NEXT: vk = VK_NEXT; break; case DIK_NUMPADENTER: vk = VK_RETURN; break; }
    if (vk) con_key(vk, dik);
}
static BYTE prev_keys[256]; static int is_state_user;
/* map: a level can't be swapped cleanly inside a running session (the menu stays up, sounds break), so the game restarts
   itself straight into the level: ismod_next.txt holds the level for the next start, solo.flag makes it skip the menu. */
static void restart_into(const char *path) {
    char f[MAX_PATH], exe[MAX_PATH];
    snprintf(f, sizeof f, "%sismod_next.txt", gamedir); FILE *o = fopen(f, "w"); if (!o) { con_print("cannot write %s", f); return; }
    fprintf(o, "%s\n", path); fclose(o);
    snprintf(f, sizeof f, "%ssolo.flag", gamedir); o = fopen(f, "w"); if (o) fclose(o);
    GetModuleFileNameA(NULL, exe, MAX_PATH);
    STARTUPINFOA si = {0}; PROCESS_INFORMATION pi; si.cb = sizeof si;
    ilog("console: restarting into %s", path);
    if (!CreateProcessA(exe, NULL, NULL, NULL, FALSE, 0, NULL, gamedir, &si, &pi)) { con_print("restart failed (%lu)", GetLastError()); return; }
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    ExitProcess(0);
}
#define GUI_MGR 0x59f8d4
#define LEAVE_GUI 0x472f80     /* GUI manager: back to the game (hides menu layers) */
#define HIDE_MENU 0x471ad0
typedef void (__thiscall *gui0_fn)(void *);
static int hide_wait, hide_again, hide_menu_req_manual, map_delay, map_quit_done; static void *world_at_map;
/* exactly what the menu's Resume button does (Game.exe 0x4740a4) */
static void hide_menu(void) {
    char *g = *(char **)GUI_OBJ; if (!g) return;
    g[0x708] = 0;
    *(int *)(g + 0x6c) = ((int (__thiscall *)(void *))0x4011b0)((void *)0x59cc78);
    ((gui0_fn)LEAVE_GUI)(g);
    /* the menu page itself is a child window of the GUI: close every child that isn't one of the GUI's permanent layers
       (those are kept in fields 0x6b0..0x73c); 0x472a90 posts the same "close" message the game uses for pages */
    int n = *(int *)(g + 0x60); void **kids = *(void ***)(g + 0x64); void *close[32]; int nc = 0;
    for (int i = 0; i < n && kids; i++) {
        void *k = kids[i]; int perm = 0;
        for (int o = 0x6a0; o < 0x740; o += 4) if (*(void **)(g + o) == k) perm = 1;
        ilog("console: gui child %d %p vtable %p%s", i, k, k ? *(void **)k : 0, perm ? " (layer)" : "");
        if (!perm && nc < 32) close[nc++] = k;
    }
    for (int i = 0; i < nc; i++) ((void (__thiscall *)(void *, void *))0x472a90)(g, close[i]);
    void *game = *(void **)0x59ee4c;
    if (game && hide_menu_req_manual) ((void (__thiscall *)(void *, int, int))0x408a40)(game, 0, 0);
    ilog("console: menu closed");
}
static void run_pending(void) {
    if (hide_wait) {      /* after "map": once the new level's world exists, take the menu down */
        void *w = *(void **)WORLD;
        if (w && w != world_at_map && --hide_wait <= 1) { hide_wait = 0; hide_menu(); hide_again = 400; }
    }
    if (hide_again > 0 && *(void **)WORLD) {     /* big levels bring the menu back while they finish loading: take it down again a couple of times */
        hide_again--;
        if (hide_again == 250 || hide_again == 100) { ilog("console: menu check"); hide_menu(); }
    }
    if (hide_menu_req) { hide_menu_req = 0; hide_menu_req_manual = 1; hide_menu(); hide_menu_req_manual = 0; }
    if (pending_restart) { pending_restart = 0; restart_into(test_buf); }
    if (!pending_set) return;
    void *gui = *(void **)GUI_OBJ; if (!gui) { pending_set = 0; con_print("map: game menu object not ready"); return; }
    if (map_delay > 0) { map_delay--; return; }
    if (*(void **)0x59ee4c && !map_quit_done) {
        /* a level is running: leave it first, exactly like the menu's "quit to main menu" (Game.exe 0x474191),
           then load the new level a moment later (loading over a live level breaks its sounds) */
        ilog("console: leaving current level");
        ((void (__thiscall *)(void *))0x401170)((void *)0x59cc78);
        ((void (__thiscall *)(void *, int))0x4025c0)((void *)0x59cc78, 1);
        ((setpage_fn)SET_PAGE)(gui, 0);
        ((char *)gui)[0x708] = 0;
        map_quit_done = 1; map_delay = 20; return;
    }
    pending_set = 0; map_quit_done = 0;
    ilog("console: map %d (%s)", pending_map, test_buf);
    world_at_map = *(void **)WORLD; hide_wait = 30;
    ((loadlevel_fn)LOAD_LEVEL)(gui, pending_map, 1);
}
static HRESULT WINAPI hook_state(IDirectInputDevice8A *d, DWORD n, LPVOID buf) {
    run_pending();
    HRESULT r = orig_state(d, n, buf);
    if (SUCCEEDED(r) && n == 256 && is_keyboard(d)) {
        is_state_user = 1; BYTE *k = buf; int was = con_open;
        for (int i = 0; i < 256; i++) { if ((k[i] & 0x80) && !(prev_keys[i] & 0x80)) key_event(i, 1); prev_keys[i] = k[i]; }
        if (con_open || was) memset(buf, 0, 256);
    }
    return r;
}
static HRESULT WINAPI hook_data(IDirectInputDevice8A *d, DWORD sz, LPDIDEVICEOBJECTDATA od, LPDWORD n, DWORD fl) {
    run_pending(); DWORD cap = n ? *n : 0;
    HRESULT r = orig_data(d, sz, od, n, fl);
    if (SUCCEEDED(r) && od && n && *n && is_keyboard(d)) {
        int was = con_open;
        for (DWORD i = 0; i < *n; i++) { DIDEVICEOBJECTDATA *e = (DIDEVICEOBJECTDATA *)((char *)od + i * sz); key_event(e->dwOfs, (e->dwData & 0x80) != 0); }
        if (con_open || was) *n = 0;
    }
    return r;
}
static void install_input_hook(void) {
    HMODULE m = LoadLibraryA("dinput8.dll"); if (!m) { ilog("console: no dinput8.dll"); return; }
    HRESULT (WINAPI *create)(HINSTANCE, DWORD, REFIID, LPVOID *, LPUNKNOWN) = (void *)GetProcAddress(m, "DirectInput8Create");
    IDirectInput8A *di = NULL; IDirectInputDevice8A *dev = NULL;
    if (!create || FAILED(create(GetModuleHandleA(NULL), DIRECTINPUT_VERSION, &IID_IDirectInput8A, (void **)&di, NULL)) || !di) { ilog("console: DirectInput8Create failed"); return; }
    if (FAILED(IDirectInput8_CreateDevice(di, &GUID_SysKeyboard, &dev, NULL)) || !dev) { ilog("console: keyboard device failed"); IDirectInput8_Release(di); return; }
    void **vt = *(void ***)dev; DWORD old;
    VirtualProtect(&vt[9], 8, PAGE_READWRITE, &old);
    orig_state = (getstate_fn)vt[9]; orig_data = (getdata_fn)vt[10];
    vt[9] = (void *)hook_state; vt[10] = (void *)hook_data;
    VirtualProtect(&vt[9], 8, old, &old);
    ilog("console: DirectInput hooked");
    IDirectInputDevice8_Release(dev); IDirectInput8_Release(di);
}
/* --- drawing --- */
typedef struct { float x, y, z, rhw; DWORD c; } VTX;
static VTX vbuf[3000]; static int nv;
static IDirect3DDevice8 *cur_dev;
static void flush(void) { if (nv) { IDirect3DDevice8_DrawPrimitiveUP(cur_dev, D3DPT_TRIANGLELIST, nv / 3, vbuf, sizeof(VTX)); nv = 0; } }
static void rect(float x0, float y0, float x1, float y1, DWORD c) {
    if (nv + 6 > 3000) flush();
    VTX a = {x0, y0, 0, 1, c}, b = {x1, y0, 0, 1, c}, d = {x0, y1, 0, 1, c}, e = {x1, y1, 0, 1, c};
    vbuf[nv++] = a; vbuf[nv++] = b; vbuf[nv++] = d; vbuf[nv++] = b; vbuf[nv++] = e; vbuf[nv++] = d;
}
#define SC 2
static void text(float x, float y, const char *t, DWORD c) {
    for (; *t; t++, x += 6 * SC) {
        int ch = (unsigned char)*t; if (ch < 32 || ch > 126) continue;
        const unsigned char *g = font5x7[ch - 32];
        for (int row = 0; row < 7; row++) {
            int run = -1;
            for (int col = 0; col <= 5; col++) {
                int on = col < 5 && (g[col] >> row) & 1;
                if (on && run < 0) run = col;
                if (!on && run >= 0) { rect(x + run * SC, y + row * SC, x + col * SC, y + (row + 1) * SC, c); run = -1; }
            }
        }
    }
}
static void draw_console(IDirect3DDevice8 *d) {
    IDirect3DSurface8 *rt = NULL; D3DSURFACE_DESC sd;
    if (FAILED(IDirect3DDevice8_GetRenderTarget(d, &rt)) || !rt) return;
    HRESULT gh = IDirect3DSurface8_GetDesc(rt, &sd); IDirect3DSurface8_Release(rt); if (FAILED(gh)) return;
    DWORD sb = 0; if (FAILED(IDirect3DDevice8_CreateStateBlock(d, D3DSBT_ALL, &sb))) return;
    cur_dev = d; nv = 0;
    IDirect3DDevice8_SetVertexShader(d, D3DFVF_XYZRHW | D3DFVF_DIFFUSE);
    IDirect3DDevice8_SetTexture(d, 0, NULL);
    IDirect3DDevice8_SetRenderState(d, D3DRS_ZENABLE, FALSE);
    IDirect3DDevice8_SetRenderState(d, D3DRS_ZWRITEENABLE, FALSE);
    IDirect3DDevice8_SetRenderState(d, D3DRS_ALPHABLENDENABLE, TRUE);
    IDirect3DDevice8_SetRenderState(d, D3DRS_SRCBLEND, D3DBLEND_SRCALPHA);
    IDirect3DDevice8_SetRenderState(d, D3DRS_DESTBLEND, D3DBLEND_INVSRCALPHA);
    IDirect3DDevice8_SetRenderState(d, D3DRS_CULLMODE, D3DCULL_NONE);
    IDirect3DDevice8_SetRenderState(d, D3DRS_LIGHTING, FALSE);
    IDirect3DDevice8_SetRenderState(d, D3DRS_FOGENABLE, FALSE);
    IDirect3DDevice8_SetRenderState(d, D3DRS_ALPHATESTENABLE, FALSE);
    IDirect3DDevice8_SetRenderState(d, D3DRS_STENCILENABLE, FALSE);
    IDirect3DDevice8_SetTextureStageState(d, 0, D3DTSS_COLOROP, D3DTOP_SELECTARG1);
    IDirect3DDevice8_SetTextureStageState(d, 0, D3DTSS_COLORARG1, D3DTA_DIFFUSE);
    IDirect3DDevice8_SetTextureStageState(d, 0, D3DTSS_ALPHAOP, D3DTOP_SELECTARG1);
    IDirect3DDevice8_SetTextureStageState(d, 0, D3DTSS_ALPHAARG1, D3DTA_DIFFUSE);
    IDirect3DDevice8_SetTextureStageState(d, 1, D3DTSS_COLOROP, D3DTOP_DISABLE);
    float W = (float)sd.Width, H = (float)sd.Height, ph = H * 0.5f, lh = 9 * SC;
    rect(0, 0, W, ph, 0xD8101418); rect(0, ph - 2, W, ph, 0xFFB08030);       /* panel + orange edge */
    int lines = (int)((ph - lh - 12) / lh), first = con_n - lines - con_scroll; if (first < 0) first = 0;
    float y = ph - lh * 2 - 8;
    for (int i = con_n - 1 - con_scroll; i >= first && y > 0; i--, y -= lh) text(6, y, con_text[i], con_text[i][0] == '>' ? 0xFFFFE080 : 0xFFE0E0E0);
    char line[170]; con_in[con_len] = 0; snprintf(line, sizeof line, "] %s%s", con_in, (GetTickCount() / 400) & 1 ? "_" : " ");
    text(6, ph - lh - 4, line, 0xFFFFFFFF);
    flush();
    IDirect3DDevice8_ApplyStateBlock(d, sb); IDirect3DDevice8_DeleteStateBlock(d, sb);
}
typedef HRESULT (WINAPI *endscene_fn)(IDirect3DDevice8 *);
static DWORD last_draw;
/* fnx_dx8.dll ends each frame with  mov eax,[driver+0x5bc] ; mov edx,[eax] ; push eax ; call [edx+0x8c]  (device->EndScene).
   Those two call instructions are redirected to here; we draw the console, then call the real EndScene. */
static HRESULT WINAPI site_endscene(IDirect3DDevice8 *d) {
    static int first = 1; if (first) { first = 0; ilog("console: frame hook running"); }
    if (con_open) draw_console(d);
    return ((endscene_fn)(*(void ***)d)[35])(d);
}
static void *site_ptr = (void *)site_endscene;
static void install_frame_hook(void) {
    HMODULE m = GetModuleHandleA("fnx_dx8.dll"); if (!m) { ilog("console: fnx_dx8.dll not loaded"); return; }
    static const unsigned sites[] = { 0x2e45, 0x3096 };
    for (int i = 0; i < 2; i++) {
        unsigned char *c = (unsigned char *)m + 0x1000 - 0x1000 + sites[i];
        if (c[0] != 0xff || (c[1] & 0xf8) != 0x90 || *(unsigned *)(c + 2) != 0x8c) { ilog("console: unexpected code at fnx_dx8+%x", sites[i]); continue; }
        DWORD old; VirtualProtect(c, 6, PAGE_EXECUTE_READWRITE, &old);
        c[0] = 0xff; c[1] = 0x15; *(void ***)(c + 2) = &site_ptr;        /* call dword ptr [site_ptr] */
        VirtualProtect(c, 6, old, &old); FlushInstructionCache(GetCurrentProcess(), c, 6);
        ilog("console: frame hook at fnx_dx8+%x", sites[i]);
    }
}

/* ---- per-level player arms: the game loads the first-person arms from the fixed name "wiz_model_first.4x3" (pushed at
   0x40a8c6 and 0x40aaf5). Those two pushes now use arms_buf, which is set from <level>.ismod ("arms=<file>") every time a
   level starts loading (hook on the level loader 0x473520). No .ismod -> the normal arms. ---- */
static char arms_buf[64] = "wiz_model_first.4x3";
static unsigned char *load_tramp;
static void set_arms_for(int num) {
    char path[300], line[200], arms[64] = "wiz_model_first.4x3";
    int r = -1; for (int i = 0; i < nredir; i++) if (redir[i].n == num) r = i;
    if (num == 0) snprintf(path, sizeof path, "%s", test_buf);
    else if (r >= 0) snprintf(path, sizeof path, "%s", redir[r].path);
    else snprintf(path, sizeof path, "levels\\campaign\\level%d\\lv%d", num, num);
    char f[400]; snprintf(f, sizeof f, "%s%s.ismod", path[1] == ':' ? "" : gamedir, path);
    FILE *h = fopen(f, "r");
    if (h) { while (fgets(line, sizeof line, h)) { line[strcspn(line, "\r\n")] = 0;
                 if (!strncmp(line, "arms=", 5) && line[5] && strlen(line + 5) < 60 && !strpbrk(line + 5, "\\/:")) strcpy(arms, line + 5); }
             fclose(h); }
    strcpy(arms_buf, arms);
    ilog("level %d (%s): arms %s", num, path, arms_buf);
}
static void __fastcall hook_load(void *self, void *edx, int num, int mode) {
    mp_active = 0;
    set_arms_for(num);
    ((loadlevel_fn)load_tramp)(self, num, mode);
}
static void install_arms_hook(void) {
    static const unsigned sites[] = { 0x40a8c6, 0x40aaf5 }; DWORD old;
    for (int i = 0; i < 2; i++) {
        unsigned char *c = (unsigned char *)sites[i];
        if (c[0] != 0x68 || *(unsigned *)(c + 1) != 0x53371c) { ilog("arms push not as expected at %x", sites[i]); return; }
    }
    unsigned char *f = (unsigned char *)0x473520;
    static const unsigned char pro[7] = {0x6a, 0xff, 0x68, 0x9b, 0xa7, 0x52, 0x00};
    if (memcmp(f, pro, 7)) { ilog("level loader not as expected"); return; }
    for (int i = 0; i < 2; i++) {
        unsigned char *c = (unsigned char *)sites[i];
        VirtualProtect(c, 5, PAGE_EXECUTE_READWRITE, &old); *(unsigned *)(c + 1) = (unsigned)arms_buf; VirtualProtect(c, 5, old, &old);
    }
    load_tramp = VirtualAlloc(NULL, 16, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    memcpy(load_tramp, pro, 7); load_tramp[7] = 0xe9; *(int *)(load_tramp + 8) = (int)(f + 7) - (int)(load_tramp + 12);
    VirtualProtect(f, 7, PAGE_EXECUTE_READWRITE, &old);
    f[0] = 0xe9; *(int *)(f + 1) = (int)(unsigned char *)hook_load - (int)(f + 5); f[5] = 0x90; f[6] = 0x90;
    VirtualProtect(f, 7, old, &old); FlushInstructionCache(GetCurrentProcess(), f, 7);
    ilog("per-level arms ready");
}
static DWORD WINAPI input_hook_thread(LPVOID p) { Sleep(500); install_input_hook(); return 0; }
BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        GetModuleFileNameA(NULL, gamedir, MAX_PATH);
        char *s = strrchr(gamedir, '\\'); if (s) s[1] = 0;
        ilog("ISModLoader %d started", ISMOD_API_VERSION);
        install_hook(); install_redirects(); install_arms_hook(); install_mp_hook(); load_plugins(); install_frame_hook(); CreateThread(NULL, 0, input_hook_thread, NULL, 0, NULL);
    }
    return TRUE;
}
