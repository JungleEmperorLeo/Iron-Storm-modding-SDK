# Iron Storm plugin SDK (first version)

Plugins are small C/C++ DLLs that add new logic to the game while a mod runs. Game.exe is never changed: the launcher
runs a temporary patched copy that loads `ISModLoader.dll`, which loads the mod's plugins.

## Writing a plugin

```c
#include "ismod.h"
static const ISModAPI *api;
static int __cdecl my_command(void) {          /* script:  native my_command player 50 */
    int who = api->get_int(0); float v = api->get_float(1);
    ...
    return 1;
}
__declspec(dllexport) void __cdecl ISMod_Init(const ISModAPI *a) {
    api = a;
    api->register_command("my_command", my_command);
}
```

The API (see `include/ismod.h`): register a script command; read its arguments (numbers, npc/player, text);
get a character object or its health; write to `ismod.log` in the game folder.

## Building

- Put the `.c` / `.cpp` files in a `plugins` folder next to your maps (`maps\mymod\plugins\`). **Build mod** and
  **Export to campaign** compile them automatically.
- Or by hand: `build_plugin.bat FOLDER` makes `FOLDER\<folder>.dll`.
- The compiler (zig, from pip) installs itself the first time; no Visual Studio needed.

## Using a plugin command in a .script

```
on use button1
    native set_health player 300
```

Arguments: npc names and `player` become entity ids, numbers become numbers, anything else is text.

## Example

`examples/set_health` adds `native set_health <npc|player> <value>`. The test map `maps\plugin_test` uses it.
`src/loader.c` is the loader itself; `../sdk/SDK_NOTES.md` lists what is known about Game.exe.
