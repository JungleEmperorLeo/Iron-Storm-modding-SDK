/* Example plugin: adds the script command
       native set_health <npc|player> <value>
   which sets a character's health directly (stock scripts cannot). */
#include "ismod.h"
static const ISModAPI *api;

static int __cdecl set_health(void) {
    int who = api->get_int(0);
    float v = api->get_float(1);
    float *h = api->health(who);
    if (!h) { api->log("set_health: %08x is not a character", who); return 0; }
    api->log("set_health %08x: %.1f -> %.1f", who, *h, v);
    *h = v;
    return 1;
}
__declspec(dllexport) void __cdecl ISMod_Init(const ISModAPI *a) {
    api = a;
    api->register_command("set_health", set_health);
}
