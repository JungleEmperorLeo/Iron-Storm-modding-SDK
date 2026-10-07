# Scripting and single-player objects

A map can have a script file next to it: `mymap.map` + `mymap.script`. When you export the map (campaign Test slot or chain levels `lv2`..`lv20`), the converter turns the script into game commands. Mistakes stop the export with the file name and line number.

## In TrenchBroom
- `trigger_script` (brush entity, use `special/trigger`): give it a `targetname`. When the player walks in, the matching `on enter` block runs.
- `door`: give it a `targetname` to use it in `open` / `close`. Set "Opens by itself" to No (`locked` 1) for a door that stays shut until the script opens it; set `wait` to -1 so it stays open.
- `func_button` (brush entity): a visible, solid button or lever. Give it a `targetname` and an `angle` (the direction it faces, like any TrenchBroom entity). When the player stands near it and presses the use key, the matching `on use` block runs. Optional keys: `range` (use distance, map units) and `cone` (use angle, degrees). The orientation settings are still being tested; if a button does not react, try a bigger `cone` (up to 180).
- `npc_soldier` and `npc_friend`: give them a `targetname` to use them in commands. Set `hidden` to Yes to keep a character out of the level until a script runs `show` on it (an ambush, a reinforcement, a cutscene entrance).

## Script file
```
# comment
on start                     # runs once when the level loads
    ...
on enter zone_name [once]    # runs when the player enters that trigger_script ("once" = first time only)
on use button_name [once]    # runs when the player presses use at that func_button
on dead npc1 npc2 ...        # runs once, when all the listed characters are dead
    ...
```
Commands go on indented lines inside a block. Numbers `x y z` are TrenchBroom map units (use the origin shown in TrenchBroom).

| Command | What it does |
|---|---|
| `speak npc ID` | The character says a stock voice line (see `STOCK_IDS.md`) |
| `subtitle ID` | Shows a stock subtitle |
| `follow npc [dist]` | The character walks behind the player (default distance 85) |
| `unfollow npc` | Stops following |
| `attack npc` | The character attacks the player |
| `attack npc other` | The character attacks another named character |
| `goto npc x y z` | Walks to a point and stops there (x y z in map units, as shown in TrenchBroom; keep the point away from walls) |
| `turn npc x y z` | Turns to face a point (x y z in map units) |
| `show npc` | Makes a hidden character appear (a character placed with `hidden` = Yes is not in the level until then) |
| `alert npc` | Puts the character on alert |
| `stop npc` | Cancels all of its orders |
| `kill npc` | Kills it |
| `remove npc` | Deletes it (no body) |
| `explode x y z` | Explosion at a point |
| `shake` | Shakes the camera |
| `atmosphere NAME` | rain, neige, neige_legere (light snow), tempete, space |
| `fog NAME` | Switches to the `env_fog` with that targetname (the others turn off) |
| `sky NAME` | Changes the sky model (sky_LV_01, sky_LV_02, sky_LV_03, sky_LV_05) |
| `movie NAME` | Plays a stock movie |
| `end_level N` | Goes to campaign level N (0 = credits) |
| `save` | Autosave (only inside `on enter`) |
| `open door` | Opens a door |
| `close door` | Closes a door |
| `set VAR N` | Sets a variable to a whole number. Variables need no declaring and all start at 0; any block can use them |
| `add VAR N` | Adds N to a variable (use a negative N to subtract) |
| `if VAR OP N` | Runs the rest of the block only if the test is true. OP is `==` or `!=`. (`<` and `>` style tests are not available: they misbehaved in testing.) To act on a count, test for the exact number, e.g. `if presses == 3`. Not allowed in `on start` |
| `wait SECONDS` | Pauses the block, then runs the rest of it (e.g. `wait 2.5`). Other blocks and buttons keep working while it waits. |

## Tips
- Soldiers shoot you on sight, so for an ambush place them with `hidden` = Yes and `show` them when the player triggers it.
- Characters on the same side cannot be ordered to attack each other (two Russian soldiers will not fight); a friend (Cecile, Mitchel) can attack a soldier and the other way round.
- `explode` is a real explosion and kills the player if he stands close; keep it away from the button.
- `follow` also switches the character to the game's follow behaviour, so it works for characters set to "stay where he is"; `unfollow` puts them back on hold.

## Example
```
on enter ambush once
    speak cecile XX1CECI015
    follow cecile 60
    attack guard_a cecile
```

## Limits
- Only stock voice lines, subtitles and movies work for `speak`/`subtitle`; your own sounds and music go in `ambient_sound` entities and the worldspawn `music` key (see below).
- `if` has no `else` and no `end`: a failed test skips everything after it in that block. Use several blocks or variables for more complex logic.
- A soldier that has started to fight forgets his patrol; scripts can re-order him (`goto`).
- Commands that are not marked as tested in the changelog may behave differently than they sound; please report anything odd.
- Scripts only run in the campaign Test slot and chain levels, not in multiplayer maps.

## Leaving a zone
`on leave <zone>` runs when the player walks out of a `trigger_script` zone (every time). For plain weather use a `trigger_weather` brush instead (no script needed): keys `enter_atmosphere`, `exit_atmosphere`, `enter_sky`, `exit_sky`, `enter_fog`, `exit_fog` (the targetname of an `env_fog` to switch to; the game cannot change a fog's colour or near distance while running, so you place several `env_fog` and switch between them like the campaign does). `weather_test.map` shows it.

## Test map
`script_all.map` + `script_all.script`: a long hall with one trigger line per command. Walk east through the lines in order.

`script_rooms.map` + `script_rooms.script`: eight separate rooms along a hallway, one group of tests per room, started with buttons (use key).

- `wait` restarts its countdown if the block runs again before it finishes (pressing a button twice quickly gives one delayed action, not two).
- `sky NAME` changes the sky mid-level (the campaign does it with the load flag set, like Level 2 and 3 zone changes). The worldspawn `sky` key sets the starting sky.
- `on dead` checks health, so do not `remove` a character that an `on dead` block is waiting for.

## Example: a door that needs two switches

```
on use switch1 once
    set s1 1
    if s2 == 1
    open exit

on use switch2 once
    set s2 1
    if s1 == 1
    open exit
```

## Fog and particle effects (map entities, single player)
- `env_fog`: up to 8 per map; give each a `targetname`. The first starts on, the rest off. Keys `color` (r g b, 0-1 or 0-255), `near`, `far`, `height_a`, `height_b` (the two values the campaign uses for height; defaults are Level 1's).
- `env_particle`: key `effect` (`steam`, `gas`, `gas_small`), `scale` (empty = default), `angles` (pitch yaw roll). Effects start with the level.

- Snow is drawn black by the game when the map has no fog entity. If a map uses weather and has no `env_fog`, the converter adds an invisible, very distant one automatically. Place your own `env_fog` to control it (any colour gives white snow with one fog; several fogs at once gave black snow in testing).

## Static meshes (`prop_static`, single player)
Places a stock model (see `STOCK_MODELS.md`, 345 non-character models) as a campaign "mover" entity. Keys: `model` (file name), `mode` (`static` or `breakable`), `angles` (pitch yaw roll), `node` (empty = whole model). `props_test.map` places a dozen to try. Whether a given model collides, and where its pivot is, is per model: test placement.

Breakable modes copy the campaign's settings: `crate` (wooden: `OBJ_obj-caisse_cassable`, `OBJ_malle-cassable`), `metal_crate` (`OBJ_caisse-metal_cassable`, `OBJ_caisse_plastique_cassable`), `vent` (`OBJ_grille_aeration`), `plank` (`obj_planche`), and `breakable` (barrel). `drop` lists what is inside the prop, e.g. `medikit shotgun_ammo` (names: medikit, small_medikit, mg_ammo, sniper_ammo, shotgun_ammo, handgun_ammo, launcher_ammo, rocket_ammo, flame_ammo, mg3_ammo, or an item number); each crate can hold something different. The pickups stay hidden until the prop breaks: the level checks the prop's health every frame and switches its contents on when it reaches 0. Place crates and trunks on the floor (bottom pivot); raise metal crates, vents, planks and barrels by half their size (centre pivot). `drop_health` (1 small, 2+ medikit) is the older key. `breakables_test.map` shows each.

## D.R.T. computers and documents (`info_drt`, `info_document`, single player)
`info_drt` places a D.R.T. terminal; using it plays its movies. Keys: `angle`, `movie` (up to 6 stock movies, space separated: XX1DRT0011, XX1DRT0012, XX3DRT0031, XX4DRT0041, XX4DRT0042, XX5DRT0051, XX5DRT0052, XX6DRT0061, XX6DRT0062), `time` (campaign values 200 to 3000; meaning unknown). `info_document` places a document to pick up and read; `text` is a stock text id (XX1DOCU000-004, XX3DOCU000-002, XX4DOCU000-001, XX5DOCU000-001, XX6DOCU000-001). `drt_test.map` has two of each.

## Turrets, dogs and mounted guns (single player)
`npc_turret` (automatic machine gun): `angle`, `yaw_min`/`yaw_max` (arc), `rate` (seconds between shots), `health`, `active`. `npc_dog`: `angle`, `explosive` (blows up when it attacks, radius 200, damage 50), `friendly`, `range`, `health`, `damage`. Turrets and dogs take `friendly` 1 to fight for the player's side (level 1's turrets are on the player's side). `weapon_mounted_mg`: a mounted gun the player can use: `angle`, `kind` (bunker, handles, launcher, launcher_stand, desk; each copies the campaign's settings for that gun), optional `pitch_range`/`yaw_range`. Turrets start switched off, like the campaign's: script `alarm on` / `alarm off` sounds or stops the alarm siren (one at each turret) and switches all turrets on or off; `turret NAME on|off` switches one turret (its targetname). Set `active` 1 to have a turret on from the start. `alarm_test.map` + `.script`: left button alarm on, right button alarm off. `enemies2_test.map` has one turret, one normal dog, one explosive dog and a mounted gun.

Helicopters are experimental: see `4_ADVANCED.md`.

## Sounds and music (single player)

- `ambient_sound` entity: `wav` = a stock sound file name (e.g. `MIT_LOIN3`, `amb_nature_b`; any .wav in the game's archives) or the name of a .wav in a `sounds` folder next to your .map. Keys: `volume` (0-1), `radius` (full volume inside, map units), `falloff` (silent beyond; blank = 2 x radius), `loop` (loop or play once), `start_on`, `targetname`.
- worldspawn `music`: a .wav that loops at the same volume everywhere. `music_volume`, `music_start` (0 = silent until the script says `music on`).
- Script: `sound NAME on|off` starts/stops an ambient_sound by targetname; `music on|off` starts/stops the music.
- Your own files: plain PCM .wav (16-bit, mono or stereo, 22050 or 44100 Hz). Compiling installs them with the level; `--package` puts them in the mod.
- Test map: `sound_test.map` (left button: music + beeper on, right button: off; the left of the room has a stock war ambience).
