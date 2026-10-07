# Iron Storm SDK notes: layer 1 (map of Game.exe v1.041)

Work in progress. Addresses are virtual addresses in Game.exe (image base 0x400000). Load `IronStorm_symbols.txt` into Ghidra
(Script Manager -> ImportSymbolsScript.py) or any disassembler to get the names below on the real code.

## What the analysis found

- 11,587 functions in Game.exe. 1,174 of them are named so far: from the game's own debug/error strings
  (`IS_WEAPON::Start`, `IS_CHARACTER::Set_Property(float)` ...), from virtual tables, and by hand.
- No C++ RTTI (no class names compiled in), so class names come from the error strings.
- 49 virtual tables identified for 47 game classes:
  FNX_GUI_LOADING_MENU, AI_BEHAVIOR, AI_GLOBAL_PARAMETER, AI_ORDER, AI_ORDER_LIST, AI_PARAMETER, AMMO_ARSENAL, ARMORY, ARSENAL, AUTO_MG, CHARACTER, DECAL, DOCUMENT, DOG, DOOR, DYNAMIC_LIGHT, EDRT, EXPLOSION, FIXED_GUN, FLAG, FOG, GIB, GRENADE, HELICOPTER, ITEM, LADDER, LENS_FLARE, LIGHTNING, MODEL, MOVER, MOVER_ANIMATION, PARTICLE_GENERATOR, POSITION, PROJECTILE, RANDOM_SOUND, RESPAWN, ROCKET, SOUND, TANK, TIMER, TRIGGER, WATER, WAVEFORM, WAY, WAYPOINT, WEAPON, ZONE

## Entity classes and properties

Every script-visible object is an entity class (`IS_<NAME>`), created by `create_entity <type>`, configured with
`set_property_int/float/string/vector <entity> <n>+BASE_PROPERTY_<CLASS> <value>`, then `start_entity`.
Each class has four property handlers (Set/Get x int/float, plus string/vector) in its virtual table; a property
number is `<base of class> + n` (e.g. character = 640 + n: 0x295 = 661 = health).
Known character fields: health = float at +0x154; weapon slots at +0x364 (16 bytes per group: +4 current weapon,
+8 ammo, +0xa count, +0xc weapon list).

## Script engine (GEL)

- Compiled scripts (.gex) run on a small VM. Engine commands (`speak`, `ai_order_reach`, `set_sky` ...) are native
  C functions linked by name: `GEL__register_native` (0x520ae0) walks a loaded script and binds every opcode-55
  call named `name` to a C function. The game calls it once per native right after loading a level script
  (0x4b1700 area). 73 natives found (`gel_natives.json`: name -> address).
- Native signature: `int __cdecl native(void)`; arguments are read through VM helpers (0x520c40 = string argument n,
  0x520d30 = number argument n; float results via 0x4f8630). Return value = script `result`.
- SDK consequence: a plugin can add NEW script commands by registering its own C function under a new name at the
  same point the game registers its natives.

## Weapons (confirmed in game: damage; flash size)

- 13 weapon ids: 0 knife, 1 handgun, 2 smg, 3 snipe, 4 shotgun, 5-8 mg1-mg4, 9 launcher, 10 rocket, 11 flame.
- Firing: per-weapon branch table at 0x5033ac (weapon id - 1); each branch creates a bullet entity (type 0xb) with
  the bullet type in property 0x2c0 and the weapon in 0x2c5.
- Damage = BULLET_TABLE[bullet type].damage (0x573870 single player, 0x5738e8 multiplayer; 3 floats per type: speed,
  speed, damage) x difficulty x hit-zone multiplier (0x54f4a0), applied in `IS_CHARACTER__take_damage` (0x42a610).
  Bullet types: handgun 2, smg 3, sniper 4, shotgun 5, mg 6/7/8.
- Per-weapon tables: group/ammo pool 0x57f9f4, zoom flag 0x57f988 + zoom 0x57f9c4 (zoom is also gated elsewhere),
  muzzle flash flag 0x57f8f4 + size 0x57f904/0x57f940, AI preferred ranges 0x57f804/0x57f840, AI score 0x57f8b8,
  noise radius 0x57f87c.
- Not found yet: fire rate / full auto (probably tied to the first-person fire animation), weapon key layout,
  the check that allows zoom.

## Plan for the next layers

2. Plugin loader: a DLL the launcher injects into the temporary ISModGame.exe; it loads the mod's plugin DLLs and
   installs hooks (fire, take_damage, level load, frame tick, native registration).
3. SDK headers/library: structures above as C++ types, helpers (find player, spawn entity, set property, register a
   script command), built with free Visual Studio Build Tools.
