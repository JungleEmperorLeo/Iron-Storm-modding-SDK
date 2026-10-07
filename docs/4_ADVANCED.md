# Advanced

## Editing a level script by hand (gexpad)
**Easiest way: the launcher's "Edit a level script (gexpad)" button** (or `python gexpad.py`). It's a Notepad-style window: File > Open a `.gex`, edit the text, Ctrl+S saves it back (the first save keeps a `.bak` of the original). Ctrl+F / F3 find, Ctrl+G go to line, Ctrl+L list the functions. A mistake (unknown label, bad operand) is reported with its line number and nothing is written. You can also drop a `.gex` onto the launcher button.

`gexedit.py` turns a compiled level script (`.gex`) into a readable text file and back, so you can edit any level's script, including the helicopter and enemy logic the map tools don't cover yet. Needs Python 3 only.

    python gexedit.py dump  test.gex -o test.gexs               # compiled script to text
    (edit test.gexs in any text editor)
    python gexedit.py build test.gexs --base test.gex -o test_new.gex
    python gexedit.py check test.gex                            # self test: dump, build, dump again, compare

`build` takes everything except the code (models tables, info, source blob) from `--base`, so use the original file you dumped. Keep a backup and copy the result over `levels\multi\test\test.gex` (or wherever the level is) to try it. Recompiling the map in TrenchBroom overwrites it, so edit after the last compile.

## Reading the text

- `:name` is a label: the start of a function (`:heli_move`, `:create_heli`) or a jump target (`:label@12`). Functions end with `:name@end`.
- One instruction per line: `call !set_property_int $id_helico "12+BASE_PROPERTY_HELICOPTER"#c 1 ;3715`. The `;3715` is the original source line (optional when you add lines).
- `call` runs an engine function (`!name`); `callf` runs a script function (`@name`); `set` assigns a variable; `jne` jumps (`@label`) when its first two operands differ. Other opcodes show as `opNN`.
- Operands: numbers, `"strings"`, `$variables` (a variable you use that doesn't exist yet is added automatically), `@labels`, `!engine functions`. Property names carry their number after `#` (hex); copy that from a neighbouring line when you add a property.
- To add behaviour, copy a similar line from the campaign's script (`python gexedit.py dump` on `levels\campaign\level1\lv1.gex`) and change its operands.

Verified on all 16 stock and compiled scripts: dump, build and dump again gives identical text.
Not verified: that the game accepts hand-edited scripts. Test in game after each change, in small steps.


## Helicopters (experimental)

**Helicopters are experimental and not reliable.** `npc_helicopter` places one and the `heli_*` commands (`heli_move`, `heli_start`, `heli_land`, `heli_takeoff`, `heli_fire`, `heli_crash`, `heli_attack`, `heli_speed`, `heli_stop`) queue orders, but in testing the move, land and take-off orders did nothing, so don't build on them. The recommended route is to edit the compiled script by hand with `gexpad` (see GEXEDIT.md) and copy the campaign's helicopter code from `lv1.gex`.
`npc_helicopter` places a helicopter (`kind` allies or enemy, `targetname`). It stays put until the script steers it, using the campaign's own helicopter settings: `heli_start NAME`, `heli_move NAME POINT` (fly to), `heli_attack NAME npc` (target a character), `heli_fire NAME POINT`, `heli_land NAME POINT`, `heli_takeoff NAME POINT`, `heli_crash NAME POINT`, `heli_speed NAME n`, `heli_stop NAME`. POINT is the targetname of a `path_corner` (as for soldiers) or plain x y z; the same works for `goto`/`turn`/`explode`. Orders only queue (up to 9); `heli_start NAME` (add `1` to loop) then carries the queue out, and must be called again whenever the helicopter has finished and you give it new orders. `heli_land`/`heli_takeoff` use only the height of the point, so fly above the pad first. What each setting does comes from reading the stock scripts, so treat the details as test-and-see. `heli_test.map` + `.script` has five buttons: start and fly, fly elsewhere, land, take off, fire.

## Custom models
First-person arms and character bodies come from each level's `player_model` (see `1_MAPPING.md`). To bring your own models in from Blender use the add-on in `blender\ironstorm_tools.zip`. The older command-line helpers (`import_model.py`, `models_install.py`, `set_arms.py`, `extract_textures.py`, `patch_game.py`) are still in `modtools`; each prints its usage when run without arguments.
