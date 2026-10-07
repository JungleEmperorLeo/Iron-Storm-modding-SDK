"""Map script files (<map>.script): small text programs the game runs when something happens in the map.

  on start                      run once when the level loads
  on enter <zone> [once]        run when the player walks into the trigger_script brush with that targetname
  on leave <zone>               run when the player walks out of that trigger_script brush again
  on use <button> [once]        run when the player presses the use key at the func_button with that targetname
  on dead <npc> [<npc> ...]     run once when all the listed characters are dead

Commands (npc = the targetname of an npc_soldier / npc_friend; "pos" = three numbers, TrenchBroom map units):
  speak npc ID          stock voice line          subtitle ID          stock subtitle text
  follow npc [dist]     walk behind the player    unfollow npc
  show npc              make a hidden character appear (it stays hidden until then)
  attack npc [npc2]     attack the player (or npc2)
  goto npc pos          run to a point            turn npc pos         face a point
  alert npc             put the soldier on alert  stop npc             cancel all of its orders
  kill npc              kill it                   remove npc           delete it (no body)
  explode pos           explosion                 shake                shake the camera
  atmosphere NAME      rain / neige / tempete / space
  sky NAME              change the sky (sky_LV_01 ... see SKIES)
  movie NAME            play a stock movie        end_level N|next     level N (0 = credits; next = the mod's next map)
  save                  autosave
  open door             open a door (by targetname)   close door   close it
  set VAR N             set a variable (all start at 0)   add VAR N   add to it (N can be negative)
  if VAR OP N           run the rest of the block only if true; OP is == or !=
  native NAME args...  a command added by a plugin (args: npc names, player, numbers, words)
  sound NAME on|off     start/stop an ambient_sound (by targetname)   music on|off   start/stop the worldspawn music
  wait SECONDS          pause, then run the rest of the block (other blocks keep running)
"""
import re

# argument kinds: npc, npc? (optional), id (a stock text/sound ID), int, int?, pos (3 numbers), name
SPEC = {
    'speak': ['npc', 'id'], 'subtitle': ['id'],
    'follow': ['npc', 'int?'], 'unfollow': ['npc'], 'show': ['npc'], 'attack': ['npc', 'npc?'],
    'goto': ['npc', 'pos'], 'turn': ['npc', 'pos'], 'alert': ['npc'], 'stop': ['npc'],
    'kill': ['npc'], 'remove': ['npc'], 'explode': ['pos'], 'shake': [],
    'atmosphere': ['name'], 'sky': ['name'], 'fog': ['name'], 'movie': ['name'], 'end_level': ['int'], 'save': [], 'wait': ['num'], 'open': ['door'], 'close': ['door'], 'alarm': ['onoff'], 'heli_move': ['heli', 'pos'], 'heli_start': ['heli', 'int?'], 'heli_stop': ['heli'], 'heli_attack': ['heli', 'npc'], 'heli_fire': ['heli', 'pos'], 'heli_land': ['heli', 'pos'], 'heli_takeoff': ['heli', 'pos'], 'heli_crash': ['heli', 'pos'], 'heli_speed': ['heli', 'num'], 'turret': ['turret', 'onoff'], 'sound': ['sound', 'onoff'], 'music': ['onoff'], 'set': ['var', 'int'], 'add': ['var', 'int'], 'if': ['var', 'op', 'int'],
}
OPS = ['==', '!=']      # < > <= >= removed: the engine's ordered compares did not behave as expected in tests
SKIES = ['sky_LV_01', 'sky_LV_02', 'sky_LV_02_02-03', 'sky_LV_03', 'sky_LV_05', 'sky_LV_05_06', 'set_sky_none']
ATMOSPHERES = ['space', 'rain', 'neige', 'neige_legere', 'tempete']

def _num(x):
    try: float(x); return True
    except ValueError: return False

def parse(text):
    """-> list of dict(kind 'enter'|'leave'|'start'|'use'|'dead', zone, once, cmds=[(cmd, [args])]); raises ValueError('line N: ...')."""
    out = []; cur = None
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split('#', 1)[0].strip()
        if not line: continue
        w = line.replace(',', ' ').split()
        if w[0] == 'on':
            if w[1:2] == ['start'] and len(w) == 2: cur = dict(kind='start', zone=None, once=True, cmds=[])
            elif w[1:2] == ['enter'] and len(w) >= 3 and (len(w) == 3 or w[3:] == ['once']):
                if not re.fullmatch(r'\w+', w[2]): raise ValueError('line %d: bad zone name %r' % (n, w[2]))
                cur = dict(kind='enter', zone=w[2], once=len(w) > 3, cmds=[])
            elif w[1:2] == ['leave'] and len(w) == 3:
                if not re.fullmatch(r'\w+', w[2]): raise ValueError('line %d: bad zone name %r' % (n, w[2]))
                cur = dict(kind='leave', zone=w[2], once=False, cmds=[])
            elif w[1:2] == ['use'] and len(w) >= 3 and (len(w) == 3 or w[3:] == ['once']):
                if not re.fullmatch(r'\w+', w[2]): raise ValueError('line %d: bad button name %r' % (n, w[2]))
                cur = dict(kind='use', zone=w[2], once=len(w) > 3, cmds=[])
            elif w[1:2] == ['dead'] and len(w) >= 3:
                for x in w[2:]:
                    if not re.fullmatch(r'\w+', x): raise ValueError('line %d: bad character name %r' % (n, x))
                cur = dict(kind='dead', zone=w[2:], once=True, cmds=[])
            else: raise ValueError('line %d: expected  on start   or   on enter <zone> [once]   or   on leave <zone>   or   on use <button> [once]   or   on dead <npc> [<npc> ...]' % n)
            out.append(cur); continue
        if cur is None: raise ValueError('line %d: command outside an "on" block' % n)
        if w[0] == 'native':               # plugin command: native NAME args...  (args: npc names, player, numbers, words)
            if len(w) < 2 or not re.fullmatch(r'[A-Za-z_]\w*', w[1]): raise ValueError('line %d: native needs a command name' % n)
            if cur['kind'] == 'start': pass
            cur['cmds'].append(('native', w[1:])); continue
        if w[0] not in SPEC: raise ValueError('line %d: unknown command %r (known: %s)' % (n, w[0], ', '.join(SPEC)))
        args = w[1:]; i = 0
        for kind in SPEC[w[0]]:
            opt = kind.endswith('?'); k = kind.rstrip('?')
            if i >= len(args):
                if opt: break
                raise ValueError('line %d: %s needs more arguments' % (n, w[0]))
            if k == 'pos':
                if not _num(args[i]) and re.fullmatch(r'[A-Za-z_]\w*', args[i]): i += 1; continue     # a path_corner name
                if i + 3 > len(args) or not all(_num(x) for x in args[i:i+3]): raise ValueError('line %d: %s needs three numbers (x y z)' % (n, w[0]))
                i += 3
            elif k == 'var':
                if not re.fullmatch(r'[A-Za-z_]\w*', args[i]): raise ValueError('line %d: bad variable name %r (letters, digits and _)' % (n, args[i]))
                i += 1
            elif k == 'op':
                if args[i] not in OPS: raise ValueError('line %d: if needs a comparison (%s), got %r' % (n, ' '.join(OPS), args[i]))
                i += 1
            elif k == 'fnum':
                if not _num(args[i]): raise ValueError('line %d: %s needs a number, got %r' % (n, w[0], args[i]))
                i += 1
            elif k == 'num':
                if not _num(args[i]) or float(args[i]) <= 0: raise ValueError('line %d: %s needs a number of seconds above 0, got %r' % (n, w[0], args[i]))
                i += 1
            elif k == 'onoff':
                if args[i] not in ('on', 'off'): raise ValueError('line %d: %s needs on or off, got %r' % (n, w[0], args[i]))
                i += 1
            elif k == 'int':
                if w[0] == 'end_level' and args[i] == 'next': i += 1; continue
                if not re.fullmatch(r'-?\d+', args[i]): raise ValueError('line %d: %s needs a whole number, got %r' % (n, w[0], args[i]))
                i += 1
            else: i += 1
        if i != len(args): raise ValueError('line %d: too many arguments for %s' % (n, w[0]))
        if cur['kind'] == 'start' and w[0] == 'if': raise ValueError('line %d: if cannot be used in an "on start" block' % n)
        if cur['kind'] == 'start' and w[0] == 'save': raise ValueError('line %d: save cannot be used in an "on start" block (use it in an "on enter" block)' % n)
        cur['cmds'].append((w[0], args))
    return out
