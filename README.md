# Iron Storm mod tools

Make maps and mods for Iron Storm (2002) with TrenchBroom, play them, and share them. Work in a **copy** of the game folder, never the Steam original. `Game.exe` is never changed (a temporary patched copy is used while a mod runs).

## Start here

1. **Open ISModLauncher** (`ISModLauncher.exe` in the Iron Storm folder, or double-click `modtools\launcher.bat`). The bar at the top shows which game folder it works on; *Change game...* lets you pick another `Game.exe` (remembered in `ismod_game.txt`). It has two tabs:
   - **Mods**: pick a mod, press *Play*. Mods live in `Mods\` (a folder or a `.zip`). *Make zip* turns a mod folder into a file you can share.
   - **Maps and tools**: pick a map and press *Compile and play*, or package it as a mod, or build a whole mod. No `.bat` files needed. It also opens the script editor and the folders.
2. **Make a map** in TrenchBroom (one-time setup below), save it in `modtools\trenchbroom\maps\`, then use the launcher's *Compile and play* button, or TrenchBroom's *Run > Compile Map*.
3. **Make it a mod** (levels in order, weapon tweaks, a title and a picture): see `docs\3_MODS.md`.

## One-time setup
1. Install Python 3 and Pillow: `python -m pip install -U pillow`
2. Export the stock textures once: run `extract_textures.bat` (or drag your Iron Storm folder onto it); it writes `modtools\trenchbroom\textures`.
3. TrenchBroom: *Preferences > Iron Storm > Game path* = `...\Iron Storm\modtools\trenchbroom`. TrenchBroom reads its game config from `%APPDATA%\TrenchBroom\games\Ironstorm\`; whenever `IronStorm.fgd` changes, copy it to `%APPDATA%\TrenchBroom\games\Ironstorm\modtools\trenchbroom\games\IronStorm\` and restart TrenchBroom.
4. New map > Iron Storm. Your own textures: PNGs in `modtools\trenchbroom\textures\<any folder>\`.

## TrenchBroom compile profiles (Run > Compile Map)
| Profile | Does |
|---|---|
| Single player: compile to Test slot | Builds the map as the campaign test level. Then *Run > Launch Engine > Play campaign Test slot* |
| Multiplayer: isdm5 / isdm6 | Builds the map as a deathmatch map with that name (play with *Launch Engine > Play isdm5 / isdm6*) |
| Build mod | Builds every map listed in the folder's `mod.json` into `Mods\` |

## Guide
- `docs\1_MAPPING.md`: entities, lighting, textures, rooms, capture the flag, single-player features.
- `docs\2_SCRIPTING.md`: script files (`.script`), every command, props, D.R.T., turrets, dogs, mounted guns, weather.
- `docs\3_MODS.md`: `mod.json`, launcher, weapon tuning, sharing.
- `docs\4_ADVANCED.md`: editing compiled scripts by hand, helicopters, models.
- `docs\STOCK_IDS.md`, `docs\STOCK_MODELS.md`: stock voice lines, movies and model names to use in maps.

## Updating
After you update the tools, rebuild the launcher once so it picks up the changes: run `modtools\build_launcher.bat` (or start it from source with `modtools\launcher.bat`).
If a mod will not load, select it in the launcher: the message under its name says what is wrong in `mod.json` (and on which line).

## What is in `modtools`
`launcher.py`, `map2is.py` (the map compiler), `gexpad.py` / `gexedit.py` (script editor), `build_mod.py`, `ismap\` (the code), `trenchbroom\` (game config and test maps), `docs\`, `sdk\` (plugin SDK), `blender\` (Blender add-on). Old helper scripts and test files are in `dev\` after you run `python tidy.py` once.
