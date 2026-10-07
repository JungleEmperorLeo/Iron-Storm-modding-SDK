# Making maps

Everything about building maps in TrenchBroom: entities, lighting, textures, rooms and the single-player (campaign) features. Setup and the first compile are in `README.md`; scripts are in `2_SCRIPTING.md`; mods and weapons are in `3_MODS.md`.

## Entities
| Entity | Notes |
|---|---|
| `worldspawn` | keys: `sky` (default sky_LV_01), `scale`, `ambient`, `lightgrid`, `shadows`, `glass_opacity` |
| `info_player_deathmatch` | spawn, 1-32, origin = feet. `team` 1/2 for team modes and CTF |
| `info_player_team1` / `info_player_team2` | capture-the-flag spawns for the USWE / Russian side (same as a deathmatch spawn with `team` set) |
| `info_player_start` | single-player start for the campaign Test slot, see below. Not used in multiplayer |
| `door` | automatic sliding door, stock model (Test slot only). Origin = bottom centre, `angle` = facing. `model`, `slide` left/right/up/down, `distance`, `speed`, `wait` (-1 stays open), `range` |
| `npc_soldier` | enemy soldier (Test slot only). `weapon` smg/mg/shotgun/sniper/rocket, `model` russian/sniper/camouflage, `health` (default 60). Holds position and fights |
| `trigger_kill` | kill zone (Test slot only), brush entity with the `special/trigger` texture: anything entering dies (with an explosion). Make it tall enough for a standing character |
| `trigger_end` | level end (Test slot only), brush entity: when you enter, the level ends and the game moves on to stock campaign level `next` (0 shows the end credits) |
| `trigger_save` | autosave checkpoint (Test slot only), brush entity: autosaves when you enter, if saving is allowed |
| `func_water` | water volume, brush entity: only the top face is drawn, not solid. Floors under it get water footsteps and impacts. Single player and campaign slots use the engine's own water entity (a rippling, sliding surface like the stock levels'): keys `tint`, `speed`, `opacity`, `grid`, `depth`, `height`, `effect 0` for the old flat plane. Multiplayer: a flat translucent plane (opacity = worldspawn `glass_opacity`). Any texture works. Test map: `water_test` |
| `item_health` | first-aid crate (Test slot only): a copy of the stock level 1 medic crate. `amount` (default 3, the stock value). Test map: `pickup_test` |
| `item_pickup` | loose pickup on the floor (Test slot only), unlimited number: `type` 0-9: medikit, small medikit, machine-gun, sniper, shotgun, handgun, launcher, rocket, flame, mg3 ammo (the names come from the game's item table; 0, 2, 3, 4 are confirmed in game); `custom` = raw type number for testing. Test map: `pickup_test` |
| `item_weapon` | weapon lying on the floor (Test slot only), unlimited number: `weapon` handgun / SMG / sniper / shotgun / MG1-4 / launcher / rocket / flame (numbers from the game's weapon table; SMG, sniper, shotgun confirmed by the stock levels, the rest untested), `ammo` (-1 = default). Test map: `pickup_test` |
| `item_armory` | weapon crate, 0-6 (0-16 in CTF). `loadout` picks one of the stock weapon sets, `team` (CTF) picks a side |
| `info_flag_team1` / `info_flag_team2` | CTF flags (USWE / Russian). Origin = bottom of the cloth, `height` raises it. Both are needed |
| `info_camera_spawn` | camera before you spawn |
| `light` | point light: `_color`, `light` (intensity), `range`, `start` |
| `light_sun` | position of the sun lens flare |
| `ambient_wind` | looping wind sound |
| `func_sector` | room volume, see Rooms |
| `func_detail`, `func_group` | brushes treated like world brushes |

### Custom crates (`item_crate`)
A weapon crate you fill yourself (campaign Test slot only, any number of crates). Set `item_1` to `item_4` to a medikit or a gun, and `ammo_1` to `ammo_4` to the number of magazines for that gun. Empty slots stay empty. Test map: `crate_test.map`.


### Smarter soldiers (campaign Test slot)
`npc_soldier` has a `behavior` key:
- `stand` (default): stands guard until he sees you.
- `chase`: slowly walks up to you from the start, even before he sees you.
- `rush`: runs to the `path_corner` named in `target` (or to where you start if `target` is empty), then fights normally.
- `patrol`: walks the `path_corner` chain starting at `target`. He stops patrolling and fights once he sees you, and does not resume the loop.

`path_corner` points have `targetname` and `target` (the next corner). Point the last one back at the first to loop. Test map: `soldier_test.map`.

### Chaining levels (campaign)
Export a map with a name `lv2` to `lv20` (the "Export as campaign level N" profiles, or `compile_map.bat map.map lv2`) and it is installed as campaign level N: `levels\campaign\levelN\lvN`. A `trigger_end` with `next` = N then leads into it. Level 1 cannot be replaced. Levels 2-6 reuse slots of the stock game (their scripts are not on disk in this install; the geometry in Models.ibf is overwritten in the working copy only). Levels above 6 are experimental. Test maps: `chain_test_a.map` (export as Test slot, ends with next=2) and `chain_test_b.map` (export as level 2, ends with credits).


### Friendly characters (`npc_friend`)
Cecile or Mitchel from level 1, fighting on your side. Keys: `who`, `behavior` (`follow` or `stand`), `distance`, `health`, `targetname`. Campaign Test slot and chain levels only. Test map: `friend_test.map`.

### Script files (`<map>.script`)
A text file next to the map, with the same name (`mymap.map` + `mymap.script`). Put a `trigger_script` brush in the map and give it a `targetname`; give any `npc_soldier` / `npc_friend` a `targetname` too. The script says what happens when the player walks into the zone:

```
# comment
on enter room_a once          (once = only the first time)
    speak cecile XX1CECI015   (a stock voice line, by its ID)
    follow cecile 60          (follow the player; the distance is optional)
    unfollow cecile
    attack cecile guard       (cecile attacks guard; "attack guard" = guard attacks the player)
    goto guard 120 40 0       (walk to a point, map units)
```
Mistakes (unknown names or commands) stop the compile with the line number. Test map: `script_test.map` + `script_test.script`. Custom text or voice lines are not possible yet; only the stock line IDs from the original levels work.

Single-player objects that are placed with entities and steered by scripts (breakable props, static meshes, D.R.T. computers and documents, turrets, dogs, mounted guns, fog and particles, weather zones) are described in `2_SCRIPTING.md`.

## Scale
`scale` (default 0.375) is game units per map unit. A player is about 72 map units tall. Textures scale with the geometry.

## Lighting
Add `light` entities and the map gets baked vertex lighting with shadows. `ambient` (0-255, default 64) is the
base level, `lightgrid` (map units, default 192) how finely large faces are subdivided for lighting, and
`shadows` 0 turns shadows off. Players and crates are tinted by the same lights. With no lights the map is full-bright.

## Textures
- Special textures (any folder): `clip`, `nodraw`, `caulk`, `sky`: solid but not drawn. `skip`, `trigger`, `hint`, `origin`: ignored.
- Transparent PNGs (any transparent pixel) are drawn as cutouts (fences, grates). A texture whose name contains
  `glass` is drawn translucent, opacity `glass_opacity` (default 0.6). Both stay solid for collision.

## Surfaces (footsteps and bullet impacts)
`surfaces.txt` maps texture names to a surface. Block form: `wood =` then one texture (or name fragment) per line.
Surface numbers: wood 2, metal 4, water 7, snow 8 (confirmed in game); ground 1 and rock 3 (guesses from the stock
maps). The `special/surf1` ... `surf8` textures force a numbered surface, and `trenchbroom\maps\surface_test.map`
is a strip of all of them for listening tests.

## Rooms (sectors and portals)
Everything is one room unless the map has `func_sector` brushes.
- Draw one box brush per room with the `special/skip` texture. Boxes must touch and must not overlap, and should
  cover all the geometry (outer walls included).
- The converter cuts the geometry at the boundaries and puts portals in every real opening where two rooms touch
  (openings under about 24 map units are ignored). It prints `sectors: N, portals: N`.
- Warnings tell you about overlapping rooms, rooms with no portal, and geometry outside every room.
- Test map: `trenchbroom\maps\sector_test.map`.

## Capture the flag
Place `info_flag_team1` and `info_flag_team2` and give some spawns `team` 1 and 2. A capture-the-flag script is
written next to the deathmatch ones (from the stock isctf3 level). Launch with the capture-the-flag entries.
Test map: `trenchbroom\maps\ctf_test.map`.

## Test maps
`enemy_test`, `door_test`, `zone_test` (single player), `water_test`, `pickup_test`, `arena_test`, `arena_lights_test`, `shadow_test`, `surface_test`, `transparent_test`, `ctf_test`, `sector_test`.

## Campaign Test slot (experimental, single player)
Compiling with the profile "Export to campaign Test slot (single player)" (map name `test`) makes your map a
single-player level: you start at `info_player_start` (or, if the map has none, the first multiplayer spawn) (feet position, its `angle` is your facing) with
all weapons, no enemies. The script is the deathmatch script plus the campaign player character from the stock
level 1 script (`ismap\solo.py`). Saving the game in the Test slot crashes the game (known issue).
- `patch_game.py` patches `Game.exe` (backup `Game.exe.orig`): New Game -> difficulty loads the Test slot
  (`--levelselect` shows the level-select page instead, `--undo` restores). It also adds an autostart hook.
- Run > Launch Engine > "Play campaign Test slot (solo)" runs `play_solo.bat`, which drops a `solo.flag` file and starts the
  game; the game deletes the flag and loads the Test level as soon as the main menu opens.
- The menu breaks with more than 10 map folders under `levels\multi`: delete `levels\multi\isdm6` while `test` exists.

### Enemy navigation
The Test export also writes `test.icp`, the AI navigation graph (format in `ismap\nav.py`): floor points on a grid
(worldspawn `navgrid`, default 96 map units), links where a soldier can walk (steps up to 20 units), routes and line of
sight between all points. Only areas connected to the player start, soldiers or spawns are kept.

### Kill and hurt zones
Each `trigger_kill` / `trigger_end` / `trigger_save` brush becomes a named event box in `test_event_boxes.4X3` (`ismap\eventbox.py`, axis-aligned
box around the brush) and a small script function the engine calls for characters inside it. Only the bounding box of the
brush is used. Test map: `zone_test` (a save strip, a kill strip, an end strip).
A hurt-over-time zone is not possible: scripts can only set a character's starting health, not the live value, and the only stock way to damage is an explosion, which kills.

## Not supported yet
Animated or swimmable water, brush doors (stock-model `door` entities work), ladders (do not work in multiplayer), custom sounds and music.

## Character models and the player's look (single player)

- `npc_soldier` → `model`: about 35 character models from the campaign (cadets, Kasakh, officers, Siberians, troopers, Ungern, scientists, workers...). Combine with `weapon` and `health` to make your own enemy types.
- `npc_friend` → `model`: a follower keeps Cecile's / Mitchel's AI and behaviour but wears any of those models. Leave it blank for their own look.
- `door` → `targetname` and "Opens by itself" = No: a door only a script opens (`open` / `close`, see `2_SCRIPTING.md`).
- worldspawn → `player_model`: the player's body (seen in cutscenes and shadows), same model names.
- First-person arms follow `player_model` automatically when that character has arms (kasakh, lobby, russian, sibbourrin1, sibsniper, supercadet, trooper); any other or no `player_model` gives the normal arms. The arms are one file for the whole game, so the last single-player map you compiled decides the arms in every level, the stock campaign included. 

## Starting weapons and ammo (per map)

worldspawn keys (single player):
- `start_weapons`: e.g. `knife handgun smg rocket`. Weapons: knife, handgun, smg, sniper, shotgun, mg, mg2, mg3, mg4, launcher, rocket, flamethrower. Blank = the normal set (knife, smg, sniper, shotgun).
- `start_ammo`: pairs, e.g. `mg 200 handgun 40 rocket 5`. Ammo types: mg (shared by the SMG and machine guns), sniper, shotgun, handgun, launcher, rocket, flamethrower, mg3. Blank = mg 50, sniper 4, shotgun 10.

## Materials

Every texture is drawn with a material. By default a texture is opaque and lit, a texture with transparent pixels is alpha-cut (fences, grates), and a texture with "glass" in its name is translucent. To change that, add a `materials.txt` next to your map (or one in `modtools` for every map). One line per texture, later lines win:

```
texture_name = kind [opacity]        # texture_name can be folder/name or just name, * allowed
water/swamp      = blend 0.8
dev/window       = reflect
lens_flare/Glow  = add
```

| kind | what it does | the game uses it for |
|---|---|---|
| `opaque` | solid, lit by the map's lights | walls, floors |
| `cut` | solid where the texture is opaque, holes where it is transparent | fences, grates, foliage |
| `blend` | translucent, still lit (opacity 0 to 1, default `glass_opacity`) | glass, level 2's swamp water (0.5 to 0.8) |
| `blend_tex` | translucent from the texture's own alpha channel (needs a texture with alpha, e.g. `LV1_flaque01`) | blood splats, mud puddles |
| `reflect` | translucent with an environment reflection, lit | helicopter window |
| `reflect_bright` | translucent with a reflection, ignores lighting | level 6 domes |
| `add` | additive glow: adds light, ignores lighting (opacity optional) | flames, halos, light shafts |

`func_water` pools are `blend` already; give the water texture a rule to set its opacity. Test map: `materials_test` (a row of panels, one per kind, and two pools). New and untested in game: please report how `reflect` and `add` look.
