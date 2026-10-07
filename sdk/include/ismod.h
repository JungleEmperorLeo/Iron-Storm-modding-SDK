/* Iron Storm mod SDK (Game.exe v1.041). Plugins are 32-bit DLLs exporting:
 *     void __cdecl ISMod_Init(const ISModAPI *api);
 * Build: build_plugin.bat <folder>   (uses the zig C compiler from pip)
 */
#pragma once
#ifdef __cplusplus
extern "C" {
#endif

#define ISMOD_API_VERSION 1

/* A new script command. Called while a level script runs; read its arguments with the get_* functions
   (argument 0 = first argument after the command name). The return value becomes the script's `result`. */
typedef int (__cdecl *ISModCommand)(void);

typedef struct ISModAPI {
    int   version;                                         /* ISMOD_API_VERSION */
    /* register a script command usable in .script files as:  native <name> <args...> */
    void  (*register_command)(const char *name, ISModCommand fn);
    int   (*get_int)(int arg);                             /* number or entity (npc / player) argument */
    float (*get_float)(int arg);                           /* number argument */
    const char *(*get_string)(int arg);                    /* text argument (valid until the next call) */
    void *(*character)(int entity_id);                     /* character object, or NULL */
    float*(*health)(int entity_id);                        /* pointer to a character's health, or NULL */
    void  (*log)(const char *fmt, ...);                    /* append a line to ismod.log in the game folder */
} ISModAPI;

#ifdef __cplusplus
}
#endif
