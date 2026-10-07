# Mods and the launcher

A mod is a folder in `Mods\` (or a `.zip` of that folder) with a `mod.json`, its compiled levels, and optionally `preview.png` (the launcher's screenshot). The launcher installs the mod you pick, starts the game straight into its first level, and when you close the game puts the stock levels, multiplayer maps and arms back.

## Make a mod
1. Put the mod's maps in their own folder, e.g. `trenchbroom\maps\mymod\` (any file names).
2. Add `mod.json` to that folder:

```
{
  "title": "My mod",
  "description": "What it is about.",
  "author": "me",
  "campaign": ["start.map", "bunker.map", "escape.map"],
  "multiplayer": {"isdm5": "arena.map"},
  "weapons": {"smg": {"damage": 12, "clip": 40}}
}
```
3. Compile with TrenchBroom's **Build mod** profile, or the launcher's **Maps and tools > Build the mod in the map's folder**. Every listed map is compiled into `Mods\mymod\`.
4. Optional: put `preview.png` next to `mod.json`. In the launcher, **Make zip** creates `Mods\mymod.zip` to share.

| Key | Meaning |
|---|---|
| `title`, `description`, `author` | Shown in the launcher |
| `campaign` | The levels in play order; the first is where the game starts. In scripts, `end_level next` (or a `trigger_end` with `next` = `next`) goes to the next one, and to the credits after the last |
| `multiplayer` | `{"isdm5": "arena.map"}` adds a map by name, or replaces a stock one (`"isdm1": "remake.map"`). Keep the total at 10 or fewer |
| `weapons` | Gun tuning for this mod, see below |

The player model and first-person arms come from each level's worldspawn `player_model` (the first level decides the arms).
If `mod.json` has a mistake the launcher shows what and where under the mod's name, and lists unknown keys or weapon settings as warnings.

## Weapon tuning (`weapons`)
Changes guns while the mod runs. The values are built into `Game.exe`, so the launcher writes them into a temporary `ISModGame.exe`; the real `Game.exe` is never changed. Enemies use the same guns, so their damage changes too. Weapons: `handgun`, `smg`, `sniper`, `shotgun`, `mg`, `launcher`, `rocket`, `flamethrower` (launcher, rocket and flamethrower only for the settings that apply to them).

| Setting | What it does | Stock values |
|---|---|---|
| `damage` | Damage per bullet (per pellet for the shotgun). Not for launcher/rocket | handgun 20, smg 8, sniper 150, shotgun 20, mg 15 |
| `flash` | Muzzle flash: `0` (none) or `[size, random extra]` | smg [0.5, 0.3], sniper [1, 0.4] |
| `clip` | Rounds per magazine | handgun 8, smg 20, sniper 5, shotgun 4, mg 35, launcher 4, rocket 1, flamethrower 100 |
| `max_ammo` | Reserve ammo you can carry (smg and mg share one pool) | mg/smg 500, sniper 25, shotgun 32, handgun 64, launcher 32, rocket 10, flamethrower 300 |
| `pickup` | Rounds in one ammo pickup | mg/smg 50, sniper 10, shotgun 8, handgun 8, launcher 4, rocket 2, flamethrower 100 |
| `speed` | Bullet speed | handgun 5000, smg 4000, sniper 10000, shotgun 3000, mg 3000 |
| `spread`, `spread_move` | Aim cone standing still / extra per unit of movement | smg 2.0 and 0.04, handgun 1.2 and 0.1, shotgun 4.5 |
| `recoil` | `[camera kick, random extra]` | smg [0.8, 0], shotgun [2.0, 0.4] |
| `ai_range`, `ai_preferred_range` | How far away enemies will use that weapon | |

Tested in game: `damage`, `flash`, `clip`. The others were found by reading `Game.exe` and are **untested**: try one at a time. The magazine you start with comes from the level (the map's start ammo), so a bigger `clip` shows after the first reload; `max_ammo` only limits what you can pick up, not what the map gives you at the start.
Not available because the game does not keep them as plain data: fire rate, reload time, shotgun pellet count, explosion damage and radius, knife damage. Moving a gun to another slot and adding a scope did not work in testing.

Example: `"weapons": {"smg": {"clip": 40, "max_ammo": 900, "spread": 0.5}}`

## Starting weapons and ammo
These are per map, in its worldspawn: `start_weapons`, `start_ammo` (see `1_MAPPING.md`).
