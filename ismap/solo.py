"""Build a single-player (campaign) level script from the stock campaign level 1 script.

The donor is levels\\campaign\\level1\\lv1.gex.  We keep only: the player character ("wiz") with its
arsenal and ammo, the sky, and the three engine hooks (client_init, server_init, server_new_player_arrival).
Instructions are copied verbatim (so string offsets into the string table stay valid) and the label table is
rebuilt for the new instruction numbering."""
import struct
from .gex import Gex

PLAYER = 'id_character_wiz'

def _chunks(d):
    out = []; o = 8
    while o < len(d):
        tag = bytes(d[o:o+4]); sz = struct.unpack_from('<I', d, o+4)[0]
        out.append([tag, bytes(d[o+8:o+sz])])
        if sz < 8: break
        o += sz
    return out, o

def _labels(payload):
    res = []; i = 0
    while i + 8 <= len(payload):
        off, n = struct.unpack_from('<II', payload, i)
        res.append((off, payload[i+8:i+8+n].split(b'\0')[0].decode())); i += 8 + n
    return res

def build(donor, start, yaw_deg, sky=None, arsenal='ALL', parts='full', tables='keep', varb='keep'):
    """start = (x, y, z) game units (feet), yaw_deg = facing in the game's convention."""
    g = Gex(donor)
    ins = g.ins; W = g.w
    chunks, endpos = _chunks(donor)
    tail = donor[endpos:]                       # GSRC etc. after the counted chunks
    lab = _labels(dict((t, p) for t, p in chunks)[b'LABE'])
    L = {n: o for o, n in lab}

    def name(k, j):
        i, opc, argc = ins[k]
        if j >= argc: return None
        o = g.op(i, j); return g.s(W[o]) if W[o] < len(g.tab) else None
    def words(k):
        i, opc, argc = ins[k]; return W[i:i+3+5*argc]

    ARS = {'ALL': ('id_arsenal_ARSENAL_ALL', 'id_ammo_arsenal_AMMO_ARSENAL_ALL')}.get(arsenal, ('id_arsenal_arsenal_wiz_test', 'id_ammo_arsenal_AMMO_ARSENAL_WIZ'))
    ents = {'full': [ARS[0], ARS[1], PLAYER], 'arsenal': [ARS[0], ARS[1]], 'none': []}[parts]
    end_editor = L['create_entity_editor@end']

    # --- entity blocks, in original order
    keep = []
    for k in range(end_editor):
        i, opc, argc = ins[k]
        if opc == 55:
            fn = name(k, 0)
            if fn == 'create_entity' and k + 1 < len(ins) and ins[k+1][1] == 15 and name(k+1, 0) in ents:
                keep += [k, k+1]
            elif fn and (fn.startswith('set_property') or fn == 'start_entity') and name(k, 1) in ents:
                keep.append(k)
    newins = [words(k) for k in keep]
    # point the player at the chosen arsenal: copy the entity operand words from one of that arsenal's own set_property calls
    def entity_operand(ename):
        for k in keep:
            if name(k, 1) == ename and ins[k][1] == 55: return words(k)[3+5:3+10]
    for n, k in enumerate(keep):
        if name(k, 1) == PLAYER and ins[k][1] == 55:
            p = name(k, 2)
            if p == '14+BASE_PROPERTY_CHARACTER': newins[n][3+15:3+20] = entity_operand(ARS[0])
            if p == '15+BASE_PROPERTY_CHARACTER': newins[n][3+15:3+20] = entity_operand(ARS[1])
            if p == '16+BASE_PROPERTY_CHARACTER':
                for j, v in enumerate(start):
                    o = 3 + 5*(3+j); iv = int(round(v)) & 0xFFFFFFFF
                    text = '%f' % v; newins[n][o:o+5] = [g.string(text), 0xFFFFFFFF, iv, struct.unpack('<I', struct.pack('<f', v))[0], iv]
            if p == '17+BASE_PROPERTY_CHARACTER':
                o = 3 + 5*3; v = float(yaw_deg); iv = int(round(v)) & 0xFFFFFFFF
                newins[n][o:o+5] = [g.string('%f' % v), 0xFFFFFFFF, iv, struct.unpack('<I', struct.pack('<f', v))[0], iv]
    newins += [words(end_editor - 1), words(end_editor)]     # return + end
    labels = [(0, 'create_entity_editor'), (len(newins) - 1, 'create_entity_editor@end')]

    def block(a, b, drop=()):
        """copy original instructions a..b inclusive, mapping labels that fall inside."""
        base = len(newins); m = {}
        for k in range(a, b + 1):
            if k in drop: continue
            m[k] = len(newins); newins.append(words(k))
        for o, n in lab:
            if a <= o <= b and n not in ('create_entity_editor', 'create_entity_editor@end'):
                nxt = [k for k in sorted(m) if k >= o]
                if nxt: labels.append((m[nxt[0]], n))
    # client_init (with the level's sky)
    block(L['client_init'], L['client_init@end'])
    # server_init: only the call to create_entity_editor
    a, b = L['server_init'], L['server_init@end']
    drop = [k for k in range(a, b + 1) if not (ins[k][1] in (6, 7) or (ins[k][1] == 3 and name(k, 0) == 'create_entity_editor'))]
    block(a, b, drop)
    block(L['server_new_player_arrival'], L['server_new_player_arrival@end'])

    newins.append(words(len(ins) - 1))      # trailing end-of-program instruction (opcode 8), as in every stock script
    labels.sort(key=lambda t: t[0])
    # label operands (type 0xFFFFFFFC: calls and jumps) carry the target instruction index in words 2 and 3
    LN = {n: o for o, n in labels}
    for w in newins:
        for j in range(w[2]):
            o = 3 + 5*j
            if w[o+1] == 0xFFFFFFFC:
                t = LN[g.s(w[o])]
                w[o+2] = t; w[o+3] = struct.unpack('<I', struct.pack('<f', float(t)))[0]
    # --- rewrite the file
    kwd = []; 
    for w in newins: kwd += w
    labe = b''.join(struct.pack('<II', o, len(n) + 1) + n.encode() + b'\0' for o, n in labels)
    tab = bytes(g.tab) + b'\0' * ((-len(g.tab)) % 4)
    rep = {b'KYWD': struct.pack('<%dI' % len(kwd), *kwd), b'NKWD': struct.pack('<I', len(newins)),
           b'LABE': labe, b'NLAB': struct.pack('<I', len(labels)),
           b'KYWT': tab, b'NKWT': struct.pack('<I', len(g.tab))}
    if tables == 'empty':          # campaign tables (e.g. TAB_ALL_EXCEPT_WIZ) refer to entities we dropped
        rep.update({b'TABL': b'', b'NTAB': struct.pack('<I', 0), b'DATA': b'', b'NDAT': struct.pack('<I', 0)})
    if varb == 'filter':           # keep only the variables this script uses, plus the gel::id_*_ type prefixes
        used = set()
        for w in newins:
            i, opc, argc = w[0], w[1], w[2]
            for j in range(argc):
                so = w[3 + 5*j]
                if so < len(g.tab): used.add(g.s(so))
        vb = dict((t, p) for t, p in chunks)[b'VARB']; i = 0; keepv = []
        while i < len(vb):
            ln = struct.unpack_from('<I', vb, i)[0]; nm = vb[i+4:i+4+ln].split(b'\0')[0].decode()
            a_, c_ = struct.unpack_from('<II', vb, i+4+ln)
            if nm[5:] in used or (a_ == 0 and c_ == 0xFFFFFFFF): keepv.append(vb[i:i+12+ln])
            i += 12 + ln
        rep[b'VARB'] = b''.join(keepv); rep[b'NVAR'] = struct.pack('<I', len(keepv))
    out = bytearray(donor[:8]); delta = 0
    for t, p in chunks:
        if t in rep: delta += len(rep[t]) - len(p); p = rep[t]
        out += t + struct.pack('<I', len(p) + 8) + p
    struct.pack_into('<I', out, 4, struct.unpack_from('<I', donor, 4)[0] + delta)
    out += tail
    return bytes(out), len(newins)


# ---------------------------------------------------------------------------------------------
# Variant that keeps a working multiplayer script intact and grafts the campaign player into it.
NBUILTIN = 51      # variable operands store 51 + VARB index (0..50 are built-ins such as 'result')

def _varb(payload):
    recs = []; i = 0
    while i < len(payload):
        ln = struct.unpack_from('<I', payload, i)[0]; nm = payload[i+4:i+4+ln].split(b'\0')[0].decode()
        t = struct.unpack_from('<I', payload, i+4+ln)[0]; n = 4 + ln + (8 if t in (0, 1, 2) else 4)
        recs.append((nm, payload[i:i+n])); i += n
    return recs

ENEMY = 'id_character_01_russian'            # template soldier in lv1 (team 2, class 7)
LOADOUT_IDS = {'knife': 0, 'handgun': 1, 'smg': 2, 'sniper': 3, 'shotgun': 4, 'mg': 5, 'mg2': 6, 'mg3': 7, 'mg4': 8,
               'launcher': 9, 'rocket': 10, 'flamethrower': 11}          # BASE_PROPERTY_ARSENAL n = has weapon n
AMMO_IDS = {'mg': 0, 'sniper': 1, 'shotgun': 2, 'handgun': 3, 'launcher': 4, 'rocket': 5, 'flamethrower': 6, 'mg3': 7}   # BASE_PROPERTY_AMMO_ARSENAL n
WEAPONS = {'smg': ('id_arsenal_ARSENAL_SMG', 'id_ammo_arsenal_AMMO_ARSENAL_MG1'),
           'mg': ('id_arsenal_ARSENAL_MG1', 'id_ammo_arsenal_AMMO_ARSENAL_MG1'),
           'shotgun': ('id_arsenal_ARSENAL_SHOTGUN', 'id_ammo_arsenal_AMMO_ARSENAL_SHOTGUN'),
           'sniper': ('id_arsenal_ARSENAL_SNIPE', 'id_ammo_arsenal_AMMO_ARSENAL_SNIPE'),
           'rocket': ('id_arsenal_rocket', 'id_ammo_arsenal_rocket')}
CHAR_MODELS = ['amedic', 'butcher', 'cadet', 'camouf', 'casque_russian', 'casque_trooper', 'cecile', 'cobaye', 'cook', 'dogmaster',
               'ecorch', 'fscient', 'gunner', 'kasakh', 'lobby', 'logan', 'masque', 'Mecca', 'medic', 'mitchell', 'nurse', 'officerone',
               'officertwo', 'relax', 'russian', 'scient', 'sibbourrin1', 'sibbourrin2', 'siberian', 'sibsniper', 'sniper', 'supercadet',
               'trooper', 'ungern', 'worker', 'wounded']     # <name>_model.4x3 in Models.ibf (character models used by the campaign)
MODELS = {'russian': 'id_model__CHR_russian_model', 'sniper': 'id_model__CHR_sniper', 'camouflage': 'id_model__CHR_camouflage'}
BEHAVIOR = 'id_ai_behavior_bouge_pas'
DOOR = 'id_door_porte_sas_1'                      # template door in lv1 (sliding armoured door)
DOOR_MODELS = {   # name: (model file, half width, half height) in game units
    'blindee': ('OBJ_porte_blindee.4x3', 15.0, 19.4), 'std': ('Porte_Std_Level05.4x3', 6.0, 13.0),
    'bunker': ('porte_bunker_lv2.4x3', 6.0, 12.6), 'cell': ('OBJ_Porte_Cellules_exp.4x3', 7.3, 16.3),
    'gare': ('obj_porte_gare.4x3', 32.7, 17.9), 'lift': ('porte_asc_ext_meta.4x3', 5.0, 15.0),
    'sas': ('Porte_Sas_Load01_Level05.4x3', 10.5, 25.5)}          # holds position, fights when it sees you

BREAK_PRESETS = {'crate': (2, 2, 6, 50.0), 'metal_crate': (4, 7, 5, 55.0), 'vent': (4, 1, 4, 50.0), 'plank': (2, 9, 8, 10.0)}


def build_mp(mp, donor, start, yaw_deg, arsenal='ALL', with_player=True, with_arrival=True, enemies=(), checkpoints=None, doors=(), zones=(), health=(), items=(), weapons=(), starts=(), buttons=(), deaths=(), player_model=None, loadout=None, ammo=None, fogs=(), fx=(), props=(), drts=(), docs=(), turrets=(), dogs=(), mguns=(), alarm=False, helis=(), sounds=(), waters=()):
    """enemies: list of dicts with pos (x,y,z), yaw, weapon (WEAPONS key), model (MODELS key), health.
    zones: list of dicts name, kind ('kill' | 'hurt'), damage (health per second, hurt), interval (seconds between hits)."""
    """mp = a multiplayer level script (bytes) that loads fine; donor = stock lv1.gex.
    Returns a script with the MP content plus the campaign player character 'wiz' and server_new_player_arrival."""
    gm, gl = Gex(mp), Gex(donor)
    mch, mend = _chunks(mp); MC = dict((t, p) for t, p in mch)
    lch, _ = _chunks(donor); LC = dict((t, p) for t, p in lch)
    mlab, llab = _labels(MC[b'LABE']), _labels(LC[b'LABE'])
    LL = {n: o for o, n in llab}; ML = {n: o for o, n in mlab}
    mvar, lvar = _varb(MC[b'VARB']), _varb(LC[b'VARB'])
    mnames = [n for n, _ in mvar]; lrec = dict(lvar); lnames = [n for n, _ in lvar]
    if 'server_new_player_arrival' in ML: raise ValueError('script already has server_new_player_arrival')

    def lname(k, j):
        i, opc, argc = gl.ins[k]
        if j >= argc: return None
        o = gl.op(i, j); return gl.s(gl.w[o]) if gl.w[o] < len(gl.tab) else None
    def lwords(k):
        i, opc, argc = gl.ins[k]; return list(gl.w[i:i+3+5*argc])
    def mwords(k):
        i, opc, argc = gm.ins[k]; return list(gm.w[i:i+3+5*argc])
    def translate(w):
        w = list(w)
        for j in range(w[2]):
            o = 3 + 5*j
            if w[o] < len(gl.tab): w[o] = gm.string(gl.s(w[o]))
            t = w[o+1]
            if NBUILTIN <= t < 0x80000000:
                nm = lnames[t - NBUILTIN]
                if nm not in mnames: mnames.append(nm); mvar.append((nm, lrec[nm]))
                w[o+1] = NBUILTIN + mnames.index(nm)
        return w

    ARS = {'ALL': ('id_arsenal_ARSENAL_ALL', 'id_ammo_arsenal_AMMO_ARSENAL_ALL')}.get(arsenal, ('id_arsenal_arsenal_wiz_test', 'id_ammo_arsenal_AMMO_ARSENAL_WIZ'))
    # entities to copy, plus everything they reference (e.g. the character's model, made by load_model)
    END = LL['create_entity_editor@end']
    made = {}                                  # entity variable -> index of the call that creates it
    for k in range(END - 1):
        if gl.ins[k][1] == 55 and lname(k, 0) in ('create_entity', 'load_model', 'load_waveform') and gl.ins[k+1][1] == 15 and lname(k+1, 1) == 'result':
            made[lname(k+1, 0)] = k
    ents = {ARS[0], ARS[1], PLAYER}
    if doors:
        ents |= {'id_waveform_door_move', 'id_waveform_door_stop'}
    uses_follow = any(c == 'follow' for z in list(zones) + list(buttons) for c, _ in z.get('cmds', [])) or any(c == 'follow' for blk in starts for c, _ in blk)
    if uses_follow: ents |= {'id_ai_behavior_follow'}
    uses_turn = any(c == 'turn' for z in list(zones) + list(buttons) for c, _ in z.get('cmds', [])) or any(c == 'turn' for blk in starts for c, _ in blk)
    if uses_turn: ents |= {'id_ai_behavior_wait_officier_002'}
    if enemies:
        ents |= {'id_model_casque_russian_model', 'id_ai_global_parameter_BON', BEHAVIOR}
        for e in enemies:
            ents |= set(WEAPONS[e.get('weapon', 'smg')]) | ({MODELS[e.get('model', 'russian')]} if e.get('model', 'russian') in MODELS else set())
    for e in enemies:                      # friendly characters cloned from a lv1 template: pull in what the template uses
        T = e.get('template')
        if T and T != ENEMY:
            for k in range(END):
                if gl.ins[k][1] == 55 and (lname(k, 0) or '').startswith('set_property') and lname(k, 1) == T:
                    ents |= {lname(k, j) for j in range(2, gl.ins[k][2])} & set(made)
    while True:
        sel = []
        for k in range(END):
            i, opc, argc = gl.ins[k]
            if opc != 55: continue
            fn = lname(k, 0)
            if fn in ('create_entity', 'load_model', 'load_waveform') and k + 1 < END and gl.ins[k+1][1] == 15 and lname(k+1, 0) in ents: sel += [k, k+1]
            elif fn and (fn.startswith('set_property') or fn == 'start_entity') and lname(k, 1) in ents: sel.append(k)
        refs = {lname(k, j) for k in sel for j in range(gl.ins[k][2])} & set(made)
        if refs <= ents: break
        ents |= refs
    if not with_player: sel = []
    graft = [translate(lwords(k)) for k in sel]

    def fconst(v):
        v = float(v); iv = int(round(v)) & 0xFFFFFFFF
        return [gm.string('%f' % v), 0xFFFFFFFF, iv, struct.unpack('<I', struct.pack('<f', v))[0], iv]
    def ent_operand(name):
        for w, k in zip(graft, sel):
            if lname(k, 1) == name and w[1] == 55: return w[3+5:3+10]
    for w, k in zip(graft, sel):
        if lname(k, 1) != PLAYER or w[1] != 55: continue
        p = lname(k, 2)
        if p == '14+BASE_PROPERTY_CHARACTER': w[18:23] = ent_operand(ARS[0])
        if p == '15+BASE_PROPERTY_CHARACTER': w[18:23] = ent_operand(ARS[1])
        if p == '16+BASE_PROPERTY_CHARACTER':
            for j, v in enumerate(start): w[3+5*(3+j):3+5*(4+j)] = fconst(v)
        if p == '17+BASE_PROPERTY_CHARACTER': w[18:23] = fconst(yaw_deg)

    # enemy soldiers: clones of the lv1 template soldier, each with its own variable
    def varop(name):
        full = 'gel::' + name
        if full not in mnames:
            src = lrec.get(full) or lrec['gel::' + ENEMY]
            oldlen = struct.unpack_from('<I', src, 0)[0]
            nm = full.encode() + b'\0'
            mnames.append(full); mvar.append((full, struct.pack('<I', len(nm)) + nm + src[4+oldlen:]))
        t = NBUILTIN + mnames.index(full)
        return [gm.string(name), t, 0, struct.unpack('<I', struct.pack('<f', float(t)))[0], 0]
    def sconst(text): return [gm.string(text), 0xFFFFFFFF, 0, 0, 0]
    def pconst(text, val): return [gm.string(text), 0xFFFFFFFF, val & 0xFFFFFFFF, struct.unpack('<I', struct.pack('<f', float(val)))[0], val & 0xFFFFFFFF]   # property names carry their number (BASE_PROPERTY_FOG = 0x880)
    def template_sel(T):
        return [k for k in range(END) if gl.ins[k][1] in (55, 15) and (
            (gl.ins[k][1] == 15 and lname(k, 0) == T) or
            (gl.ins[k][1] == 55 and lname(k, 0) in ('create_entity', 'load_model', 'load_waveform') and k + 1 < END and gl.ins[k+1][1] == 15 and lname(k+1, 0) == T) or
            (gl.ins[k][1] == 55 and (lname(k, 0) or '').startswith(('set_property', 'start_entity')) and lname(k, 1) == T))]
    def iconst(v): return [gm.string('%d' % v), 0xFFFFFFFF, v & 0xFFFFFFFF, struct.unpack('<I', struct.pack('<f', float(v)))[0], v & 0xFFFFFFFF]
    tvar = 'gel::' + ENEMY
    cmtpl = [k for k in range(END - 1) if gl.ins[k][1] == 55 and lname(k, 0) == 'load_model' and lname(k+1, 0) == 'id_model__DOOR_porte_blindee_model']
    cloaded = {}
    for m in [e.get('model') if e.get('keep') else e.get('model', 'russian') for e in enemies] + [player_model]:   # extra character models: load <name>_model.4x3 like the campaign does
        if m and m not in MODELS and m not in cloaded:
            mv = 'id_model__CHR_custom_%d' % len(cloaded)
            w1, w2 = translate(lwords(cmtpl[0])), translate(lwords(cmtpl[0] + 1))
            w1[8:13] = sconst(m + '_model.4x3'); w2[3:8] = varop(mv)
            graft[0:0] = [w1, w2]; cloaded[m] = mv; sel = [None, None] + list(sel)
    if loadout is not None or ammo is not None:     # starting weapons / ammo: the values of the player's arsenal entities
        for idx, k in enumerate(sel):
            if k is None or gl.ins[k][1] != 55 or lname(k, 0) != 'set_property_int': continue
            who, p = lname(k, 1), lname(k, 2) or ''
            if loadout is not None and who == ARS[0] and p.endswith('+BASE_PROPERTY_ARSENAL'):
                graft[idx][18:23] = iconst(1 if int(p.split('+')[0]) in loadout else 0)
            if ammo is not None and who == ARS[1] and p.endswith('+BASE_PROPERTY_AMMO_ARSENAL'):
                graft[idx][18:23] = iconst(int(ammo.get(int(p.split('+')[0]), 0)))
    if player_model:           # the player's third-person body (seen in cutscenes and shadows; first-person arms are separate)
        hit = 0
        for idx, k in enumerate(sel):
            if k is not None and gl.ins[k][1] == 55 and lname(k, 0) == 'set_property_int' and lname(k, 1) == PLAYER and lname(k, 2) == '0+BASE_PROPERTY_CHARACTER':
                graft[idx][18:23] = varop(MODELS[player_model] if player_model in MODELS else cloaded[player_model]); hit += 1
        if not hit: raise ValueError('player model property not found')
    for n, e in enumerate(enemies):
        nm = 'id_character_enemy_%02d' % (n + 1)
        wpn = WEAPONS[e.get('weapon', 'smg')]
        T = e.get('template', ENEMY)
        for k in template_sel(T):
            w = list(lwords(k))
            for j in range(w[2]):                       # the soldier's own variable -> this clone's
                o = 3 + 5*j
                if w[o] < len(gl.tab) and gl.s(w[o]) == T: w[o:o+5] = [0, 0, 0, 0, 0]; w[o+1] = 0xFFFFFFFE
            w = translate(w)
            for j in range(w[2]):
                o = 3 + 5*j
                if w[o+1] == 0xFFFFFFFE: w[o:o+5] = varop(nm)
            if w[1] == 55:
                p = lname(k, 2)
                if p == '0+BASE_PROPERTY': w[18:23] = sconst(nm[13:])
                if p == '16+BASE_PROPERTY_CHARACTER':
                    for j, v in enumerate(e['pos']): w[3+5*(3+j):3+5*(4+j)] = fconst(v)
                if p == '17+BASE_PROPERTY_CHARACTER': w[18:23] = fconst(e.get('yaw', 0.0))
                if e.get('hold') and p == '20+BASE_PROPERTY_CHARACTER': w[18:23] = varop(BEHAVIOR)     # stay put
                if e.get('keep') and e.get('model') and p == '0+BASE_PROPERTY_CHARACTER':   # a friend with its own model
                    m = e['model']; w[18:23] = varop(MODELS[m] if m in MODELS else cloaded[m])
                if not e.get('keep'):      # friends keep the template's own model, weapons and behaviour
                    if p == '0+BASE_PROPERTY_CHARACTER':
                        m = e.get('model', 'russian'); w[18:23] = varop(MODELS[m] if m in MODELS else cloaded[m])
                    if p == '14+BASE_PROPERTY_CHARACTER': w[18:23] = varop(wpn[0])
                    if p == '15+BASE_PROPERTY_CHARACTER': w[18:23] = varop(wpn[1])
                    if p == '20+BASE_PROPERTY_CHARACTER': w[18:23] = varop(BEHAVIOR)
                if p == '21+BASE_PROPERTY_CHARACTER': w[18:23] = fconst(e.get('health', 60))
                for q, v in e.get('props', {}).items():
                    if p == '%d+BASE_PROPERTY_CHARACTER' % q: w[18:23] = iconst(v)
            if w[1] == 55 and lname(k, 0) == 'start_entity':
                for q, v in e.get('after', []):        # set_property_int <clone> <q> <v> after the start
                    sp = [w[0], 55, 4] + sconst('set_property_int')[:1] + [0xFFFFFFF1, 0xFFFFFFFF, 0xBF800000, 0] \
                         + varop(nm) + [gm.string('%d+BASE_PROPERTY_CHARACTER' % q), 0xFFFFFFFF, 640 + q, struct.unpack('<I', struct.pack('<f', 640.0 + q))[0], 640 + q] + iconst(v)
                    graft.append(w); w = sp
            graft.append(w)

    # doors: clones of the lv1 sliding door, set up like the automatic multiplayer doors (isctf1): open when someone comes near
    mtpl = [k for k in range(END - 1) if gl.ins[k][1] == 55 and lname(k, 0) == 'load_model' and lname(k+1, 0) == 'id_model__DOOR_porte_blindee_model']
    loaded = {}
    for n, e in enumerate(doors):
        mfile = e.get('file') or DOOR_MODELS[e.get('model', 'blindee')][0]
        if mfile not in loaded:
            mv = 'id_model__DOOR_custom_%d' % len(loaded)
            w1, w2 = translate(lwords(mtpl[0])), translate(lwords(mtpl[0] + 1))
            w1[8:13] = sconst(mfile); w2[3:8] = varop(mv)
            graft += [w1, w2]; loaded[mfile] = mv
        nm = 'id_door_custom_%02d' % (n + 1)
        for k in template_sel(DOOR):
            w = list(lwords(k))
            for j in range(w[2]):
                o = 3 + 5*j
                if w[o] < len(gl.tab) and gl.s(w[o]) == DOOR: w[o:o+5] = [0, 0xFFFFFFFE, 0, 0, 0]
            w = translate(w)
            for j in range(w[2]):
                o = 3 + 5*j
                if w[o+1] == 0xFFFFFFFE: w[o:o+5] = varop(nm)
            if w[1] == 55:
                p = lname(k, 2)
                def fset(v): w[18:23] = fconst(v)
                if p == '0+BASE_PROPERTY': w[18:23] = sconst(nm[8:])
                if p == '0+BASE_PROPERTY_DOOR': w[18:23] = varop(loaded[mfile])
                if p == '3+BASE_PROPERTY_DOOR': fset(e['yaw'])
                if p == '4+BASE_PROPERTY_DOOR':
                    for j, v in enumerate(e['closed']): w[3+5*(3+j):3+5*(4+j)] = fconst(v)
                if p == '5+BASE_PROPERTY_DOOR':
                    for j, v in enumerate(e['open']): w[3+5*(3+j):3+5*(4+j)] = fconst(v)
                if p == '6+BASE_PROPERTY_DOOR': fset(e.get('speed', 0.3))
                if p == '11+BASE_PROPERTY_DOOR': w[18:23] = varop('id_waveform_door_move')
                if p == '12+BASE_PROPERTY_DOOR': fset(e.get('wait', 3.0))
                for q, v in (((13, 1), (14, 0), (15, 0), (19, 0)) if e.get('locked') else ((13, 1), (14, 1), (15, 1), (19, 1))):   # locked = lv1 scripted-door values
                    if p == '%d+BASE_PROPERTY_DOOR' % q: w[18:23] = iconst(v)
                if p == '17+BASE_PROPERTY_DOOR': fset(e.get('range', 50.0))
            graft.append(w)

    # health pickups: clones of the lv1 'medic' armory (the first-aid crate)
    MEDIC = 'id_armory_ARMORY_medic'
    for n, e in enumerate(health):
        nm = 'id_armory_health_%02d' % (n + 1)
        for k in template_sel(MEDIC):
            w = list(lwords(k))
            for j in range(w[2]):
                o = 3 + 5*j
                if w[o] < len(gl.tab) and gl.s(w[o]) == MEDIC: w[o:o+5] = [0, 0xFFFFFFFE, 0, 0, 0]
            w = translate(w)
            for j in range(w[2]):
                o = 3 + 5*j
                if w[o+1] == 0xFFFFFFFE: w[o:o+5] = varop(nm)
            if w[1] == 55:
                p = lname(k, 2)
                if p == '0+BASE_PROPERTY': w[18:23] = sconst(nm[10:])
                if p == '1+BASE_PROPERTY':
                    for j, v in enumerate(e['pos']): w[3+5*(3+j):3+5*(4+j)] = fconst(v)
                if p == '0+BASE_PROPERTY_ARMORY': w[18:23] = fconst(e.get('yaw', 0.0))
                if p == '1+BASE_PROPERTY_ARMORY': w[18:23] = varop('id_model_armory')
                if p == '20+BASE_PROPERTY_ARMORY': w[18:23] = fconst(e.get('amount', 3.0))
                if 'slots' in e:    # configurable crate: up to 4 weapons (game weapon ids, -1 = empty) with magazines each, optional medikit
                    for q in range(4):
                        if p == '%d+BASE_PROPERTY_ARMORY' % (2 + q): w[18:23] = iconst(e['slots'][q])
                        if p == '%d+BASE_PROPERTY_ARMORY' % (6 + q): w[18:23] = iconst(e['mags'][q])
                    if p == '10+BASE_PROPERTY_ARMORY': w[18:23] = iconst(3 if e.get('medic') else 0)
            graft.append(w)

    # loose weapons lying on the floor: clones of the lv1 WEAPON entity 'armurerie_smg' (type = index in the game's weapon table:
    # 0 knife, 1 handgun, 2 smg, 3 snipe, 4 shotgun, 5-8 mg1-mg4, 9 launcher, 10 rocket, 11 flame, 12 fire)
    WPN = 'id_weapon_armurerie_smg'
    for n, e in enumerate(weapons):
        nm = 'id_weapon_pickup_%02d' % (n + 1)
        for k in template_sel(WPN):
            w = list(lwords(k))
            for j in range(w[2]):
                o = 3 + 5*j
                if w[o] < len(gl.tab) and gl.s(w[o]) == WPN: w[o:o+5] = [0, 0xFFFFFFFE, 0, 0, 0]
            w = translate(w)
            for j in range(w[2]):
                o = 3 + 5*j
                if w[o+1] == 0xFFFFFFFE: w[o:o+5] = varop(nm)
            if w[1] == 55:
                p = lname(k, 2)
                if p == '0+BASE_PROPERTY': w[18:23] = sconst(nm[10:])
                if p == '1+BASE_PROPERTY':
                    for j, v in enumerate(e['pos']): w[3+5*(3+j):3+5*(4+j)] = fconst(v)
                if p == '1+BASE_PROPERTY_WEAPON': w[18:23] = fconst(e.get('yaw', 0.0))
                if p == '2+BASE_PROPERTY_WEAPON': w[18:23] = fconst(90.0)
                if p == '3+BASE_PROPERTY_WEAPON': w[18:23] = fconst(0.0)
                if p == '0+BASE_PROPERTY_WEAPON': w[18:23] = iconst(int(e['weapon']))
                if p == '7+BASE_PROPERTY_WEAPON': w[18:23] = iconst(int(e.get('ammo', -1)))
            graft.append(w)

    # loose pickups (ITEM entities): types as named in the game's item table: 0 medikit, 1 small medikit, 2 mg ammo, 3 sniper, 4 shotgun, 5 handgun, 6 launcher, 7 rocket, 8 flame, 9 mg3 (0, 2, 3, 4 seen in the stock levels)
    ITEM = 'id_item_ITEM_001'
    for n, e in enumerate(items):
        nm = 'id_item_pickup_%02d' % (n + 1)
        for k in template_sel(ITEM):
            w = list(lwords(k))
            for j in range(w[2]):
                o = 3 + 5*j
                if w[o] < len(gl.tab) and gl.s(w[o]) == ITEM: w[o:o+5] = [0, 0xFFFFFFFE, 0, 0, 0]
            w = translate(w)
            for j in range(w[2]):
                o = 3 + 5*j
                if w[o+1] == 0xFFFFFFFE: w[o:o+5] = varop(nm)
            if w[1] == 55:
                p = lname(k, 2)
                if p == '0+BASE_PROPERTY': w[18:23] = sconst(nm[8:])
                if p == '1+BASE_PROPERTY':
                    for j, v in enumerate(e['pos']): w[3+5*(3+j):3+5*(4+j)] = fconst(v)
                rot = e.get('rot', (e.get('yaw', 0.0), 0.0, 0.0))     # item properties 1/2/3 = yaw, pitch, roll (the campaign lays medikits on their side inside crates: pitch 92, roll -90)
                if p == '1+BASE_PROPERTY_ITEM': w[18:23] = fconst(rot[0])
                if p == '2+BASE_PROPERTY_ITEM': w[18:23] = fconst(rot[1])
                if p == '3+BASE_PROPERTY_ITEM': w[18:23] = fconst(rot[2])
                if p == '0+BASE_PROPERTY_ITEM': w[18:23] = iconst(int(e.get('type', 0)))
            if e.get('hold') and w[1] == 55 and lname(k, 0) == 'start_entity': continue     # a prop's contents: started by the clock when the prop breaks
            graft.append(w)

    # kill / hurt zones: script functions the engine calls for characters inside the zone's event box (Event_<name>)
    def find(pred): return next(k for k in range(len(gl.ins)) if pred(k))
    def tl(k): return translate(lwords(k))
    def with_ops(k, **patch):
        w = tl(k)
        for j, op in patch.items(): w[3+5*int(j[1:]):8+5*int(j[1:])] = op
        return w
    def lab(name): return [gm.string(name), 0xFFFFFFFC, 0, 0, 0]
    K_REACH = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'ai_order_reach' and gl.ins[k][2] == 8)
    K_ATT = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'ai_order_attack' and gl.ins[k][2] == 4)
    K_FOL = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'ai_order_follow' and lname(k, 2) == PLAYER and gl.ins[k][2] == 4)
    K_SPEAK = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'speak' and gl.ins[k][2] == 6 and lname(k, 1) != PLAYER)
    K_UNF = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'ai_remove_order_follow' and gl.ins[k][2] == 3 and lname(k, 2) == PLAYER)
    K_FLAGC = find(lambda k: gl.ins[k][1] == 32 and lname(k, 0) == 'bombedone1' and lname(k, 1) == '0')
    K_FLAGS = find(lambda k: gl.ins[k][1] == 15 and lname(k, 0) == 'bombedone1' and lname(k, 1) == '1')
    def reach_ins(char, pos): return with_ops(K_REACH, a1=char, a2=fconst(pos[0]), a3=fconst(pos[1]), a4=fconst(pos[2]))
    # use-buttons: clones of the lv1 'TRIGGER' entity (the game calls <name>_server when the player presses use near it)
    TRG = 'id_trigger_drt_bedroom_01'
    for n, e in enumerate(buttons):
        nm = 'id_trigger_btn_%02d' % (n + 1)
        for k in template_sel(TRG):
            w = list(lwords(k))
            for j in range(w[2]):
                o = 3 + 5*j
                if w[o] < len(gl.tab) and gl.s(w[o]) == TRG: w[o:o+5] = [0, 0, 0, 0, 0]; w[o+1] = 0xFFFFFFFE
            w = translate(w)
            for j in range(w[2]):
                o = 3 + 5*j
                if w[o+1] == 0xFFFFFFFE: w[o:o+5] = varop(nm)
            if w[1] == 55:
                p = lname(k, 2)
                if p == '0+BASE_PROPERTY': w[18:23] = sconst(nm[11:])
                if p == '1+BASE_PROPERTY':
                    for j, v in enumerate(e['pos']): w[3+5*(3+j):3+5*(4+j)] = fconst(v)
                if p == '0+BASE_PROPERTY_TRIGGER':
                    for j, v in enumerate((90.0, 0.0, e.get('yaw', 0.0))): w[3+5*(3+j):3+5*(4+j)] = fconst(v)
                if p == '1+BASE_PROPERTY_TRIGGER': w[18:23] = sconst(e['name'])
                if p == '2+BASE_PROPERTY_TRIGGER': w[18:23] = fconst(e.get('cone', 90.0))
                if p == '3+BASE_PROPERTY_TRIGGER': w[18:23] = fconst(e.get('cone', 90.0))
                if p == '4+BASE_PROPERTY_TRIGGER': w[18:23] = fconst(e.get('range', 24.0))
                if p == '5+BASE_PROPERTY_TRIGGER': w[18:23] = fconst(-1.0)      # uses left: -1 = unlimited (stock lv1 button had 2)
            graft.append(w)

    def call(fn, *ops): return [0, 55, 1 + len(ops)] + [gm.string(fn), 0xFFFFFFF1, 0xFFFFFFFF, 0xBF800000, 0] + [x for o in ops for x in o]
    def setprop(who, q, val): return call('set_property_int', who, [gm.string('%d+BASE_PROPERTY_CHARACTER' % q), 0xFFFFFFFF, 640 + q, struct.unpack('<I', struct.pack('<f', 640.0 + q))[0], 640 + q], val)
    def newvar(nm, like):
        full = 'gel::' + nm
        if full not in mnames:
            src = lrec['gel::' + like]; oldlen = struct.unpack_from('<I', src, 0)[0]; nb = full.encode() + b'\0'
            mnames.append(full); mvar.append((full, struct.pack('<I', len(nb)) + nb + src[4+oldlen:]))
        t = NBUILTIN + mnames.index(full)
        return [gm.string(nm), t, 1, struct.unpack('<I', struct.pack('<f', float(t)))[0], 0]
    def waitvars(k): return newvar('script_wait_on_%d' % k, 'bombedone1'), newvar('script_wait_t_%d' % k, 'mon_timer')
    k_clr = find(lambda k: gl.ins[k][1] == 15 and lname(k, 0) == 'mon_timer' and lname(k, 1) == '0.0')
    waits = []                        # (timer number, seconds, remaining commands, label base) -- run by the clock box
    def emit(cmds, base):
        """script-file commands -> (instructions, {label: index}); typed args: ('npc', var) ('num', v) ('str', s) ('int', v)"""
        ins = []; inner = {}; ifs = []
        for ci, (cmd, a) in enumerate(cmds):
            if cmd == 'wait':             # start timer k and stop here; the clock runs the rest when it expires
                k = len(waits) + 1; waits.append((k, float(a[0][1]), cmds[ci+1:], '%s@w%d' % (base, k)))
                FL, ACC = waitvars(k)
                ins += [with_ops(k_clr, a0=ACC), with_ops(K_FLAGS, a0=FL, a1=iconst(1))]
                break
            who = varop(a[0][1]) if a and a[0][0] == 'npc' else None
            num = lambda t: fconst(t[1]); st = lambda t: sconst(t[1]); it = lambda t: iconst(int(t[1]))
            if cmd == 'speak': ins.append(call('speak', who, st(a[1]), iconst(3), iconst(0), iconst(0)))
            elif cmd == 'subtitle': ins.append(call('launch_subtitle', st(a[0])))
            elif cmd == 'follow': ins += [setprop(who, 20, varop('id_ai_behavior_follow')), call('ai_order_follow', who, PLAYER_OP, iconst(int(a[1][1]) if len(a) > 1 else 85))]
            elif cmd == 'unfollow': ins += [setprop(who, 20, varop(BEHAVIOR)), call('ai_remove_all_objectives', who)]
            elif cmd == 'show': ins.append(setprop(who, 11, iconst(0)))
            elif cmd == 'attack': ins.append(call('ai_order_attack', who, varop(a[1][1]) if len(a) > 1 else PLAYER_OP, iconst(100)))
            elif cmd == 'goto': ins += [setprop(who, 20, varop(BEHAVIOR))]; ins.append(call('ai_order_reach', who, num(a[1]), num(a[2]), num(a[3]), iconst(0), iconst(0), iconst(10)))
            elif cmd == 'turn': ins += [setprop(who, 20, varop('id_ai_behavior_wait_officier_002')), call('ai_order_turn', who, num(a[1]), num(a[2]), num(a[3]), iconst(100))]
            elif cmd == 'alert': ins.append(call('ai_force_alert', who))
            elif cmd == 'stop': ins.append(call('ai_remove_all_objectives', who))
            elif cmd == 'kill': ins.append(call('mortar_explosion_on_character', who))
            elif cmd == 'remove': ins.append(call('delete_entity', who))
            elif cmd == 'explode': ins.append(call('mortar_explosion_on_ground', num(a[0]), num(a[1]), num(a[2]), iconst(0), iconst(0), iconst(1)))
            elif cmd == 'shake': ins.append(call('shake_camera', iconst(1), iconst(0), iconst(3), iconst(3)))
            elif cmd == 'atmosphere': ins.append(call('set_atmosphere', st(a[0])))
            elif cmd == 'fog':      # switch fog like the campaign: property 7 of each fog entity is its on/off switch
                for fi, fg in enumerate(fogs):
                    ins.append(call('set_property_int', varop('id_fog_map_%02d' % (fi + 1)), pconst('7+BASE_PROPERTY_FOG', 0x887), iconst(1 if fg['name'] == a[0][1] else 0)))
            elif cmd.startswith('heli_'):       # helicopters, steered like the campaign's heli_* functions (property settings on the helicopter entity)
                hv = varop(a[0][1]); hb = LL['create_heli']
                def hprop(prop, typ):
                    return find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == typ and lname(k, 2) == prop + '+BASE_PROPERTY_HELICOPTER')
                def hset(prop, typ, **vals): ins.append(with_ops(hprop(prop, typ), a1=hv, **vals))
                if cmd == 'heli_move': hset('2', 'set_property_vector', a3=num(a[1]), a4=num(a[2]), a5=num(a[3]))
                elif cmd == 'heli_start': hset('5', 'set_property_int', a3=iconst(int(a[1][1]) if len(a) > 1 else 0)); hset('3', 'set_property_int', a3=iconst(1))
                elif cmd == 'heli_stop': hset('15', 'set_property_int', a3=iconst(1))
                elif cmd == 'heli_attack': hset('7', 'set_property_int', a3=varop(a[1][1])); hset('4', 'set_property_int', a3=iconst(1))
                elif cmd == 'heli_fire': hset('9', 'set_property_vector', a3=num(a[1]), a4=num(a[2]), a5=num(a[3]))
                elif cmd == 'heli_land': hset('11', 'set_property_vector', a3=num(a[1]), a4=num(a[2]), a5=num(a[3]))
                elif cmd == 'heli_takeoff': hset('10', 'set_property_vector', a3=num(a[1]), a4=num(a[2]), a5=num(a[3]))
                elif cmd == 'heli_crash': hset('14', 'set_property_vector', a3=num(a[1]), a4=num(a[2]), a5=num(a[3]))
                elif cmd == 'heli_speed': hset('16', 'set_property_float', a3=num(a[1]))
            elif cmd in ('sound', 'music'):    # ambient sounds: property 7 = playing (as the campaign's alarm script)
                v = int(a[-1][1])
                k_snd = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'set_property_int' and lname(k, 1) == 'id_sound_alarme_qg' and lname(k, 2) == '7+BASE_PROPERTY_SOUND' and lname(k, 3) == '1')
                t = a[0][1] if cmd == 'sound' else 'id_sound_snd_music'
                ins.append(with_ops(k_snd, a1=varop(t), a3=iconst(v)))
            elif cmd in ('alarm', 'turret'):    # like the campaign's alarm script: turrets' property 0 and the alarm sounds' property 7 switched on/off
                v = int(a[-1][1])
                k_amg = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'set_property_int' and lname(k, 2) == '0+BASE_PROPERTY_AUTO_MG' and lname(k, 3) == '1')
                targets = [a[0][1]] if cmd == 'turret' else ['id_auto_mg_map_%02d' % (n + 1) for n in range(len(turrets))]
                for t in targets: ins.append(with_ops(k_amg, a1=varop(t), a3=iconst(v)))
                if cmd == 'alarm':
                    k_snd = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'set_property_int' and lname(k, 1) == 'id_sound_alarme_qg' and lname(k, 2) == '7+BASE_PROPERTY_SOUND' and lname(k, 3) == '1')
                    for n in range(max(1, len(turrets))): ins.append(with_ops(k_snd, a1=varop('id_sound_alarm_map_%02d' % (n + 1)), a3=iconst(v)))
            elif cmd == 'sky': ins.append(call('set_sky', st(a[0]), iconst(1)))
            elif cmd == 'movie': ins.append(call('play_movie', st(a[0])))
            elif cmd in ('set', 'add', 'if'):     # script variables: float globals sv_<name> starting at 0 (same kind of variable as the wait timers)
                V = newvar('sv_' + a[0][1], 'mon_timer')
                if cmd == 'set': ins.append(with_ops(k_clr, a0=V, a1=fconst(float(a[1][1]))))
                elif cmd == 'add':
                    ka = find(lambda k: gl.ins[k][1] == 22 and lname(k, 0) == 'mon_timer' and lname(k, 1) == 'fresult')
                    TMP = newvar('sv__amount', 'mon_timer')      # add needs a variable operand (a constant adds to the raw bits)
                    ins += [with_ops(k_clr, a0=TMP, a1=fconst(float(a[1][1]))), with_ops(ka, a0=V, a1=TMP)]
                else:                            # skip the rest of the block unless the test holds
                    op = a[1][1]; v = int(a[2][1]); lbl = '%s@if%d' % (base, ci); ifs.append(lbl)
                    # jump ops: 31 = equal, 32 = not equal, 33 = greater (unconfirmed), 36 = less-or-equal (tested: '>= 3' fired on press 4)
                    # whole numbers: >= v skips when <= v-1;  > v skips when <= v;  <= v skips when > v;  < v skips when > v-1
                    jop, jv = {'==': (32, v), '!=': (31, v), '<=': (33, v), '<': (33, v - 1), '>=': (36, v - 1), '>': (36, v)}[op]
                    kj = find(lambda k: gl.ins[k][1] == jop and gl.ins[k][2] == 3)
                    ins.append(with_ops(kj, a0=V, a1=fconst(float(jv)), a2=lab(lbl)))
            elif cmd == 'native':                # a plugin command: op55 call by name
                ops = []
                for t in a[1:]:
                    ops.append(varop(t[1]) if t[0] == 'npc' else PLAYER_OP if t[0] == 'player' else fconst(t[1]) if t[0] == 'num' else sconst(t[1]))
                ins.append(call(a[0][1], *ops))
            elif cmd in ('open', 'close'):     # door state: 0 = open, 1 = closed (lv4 lifts)
                dk = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'set_property_int' and lname(k, 2) == '8+BASE_PROPERTY_DOOR')
                ins.append(with_ops(dk, a1=varop(a[0][1]), a3=iconst(0 if cmd == 'open' else 1)))
            elif cmd == 'end_level': ins.append(call('end_of_level', it(a[0])))
            elif cmd == 'save':
                lbl = '%s@save%d' % (base, ci)
                ins += [tl(K_CS), with_ops(K_C1, a2=lab(lbl)), tl(K_AS)]; inner[lbl] = len(ins)
        for lbl in ifs: inner[lbl] = len(ins)      # a failed 'if' jumps to the end of the block
        return ins, inner
    PLAYER_OP = tl(K_FOL)[3+10:3+15]
    K_CS = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'can_save')
    K_AS = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'autosave')
    K_C1 = find(lambda k: gl.ins[k][1] == 32 and lname(k, 0) == 'result' and lname(k, 1) == '1')
    zfun = []                         # (function name, [instructions], {label name: index inside the function})
    if zones:
        k_gcb = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'get_character_in_box_id')
        k_mort = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'mortar_explosion_on_character' and gl.ins[k][2] == 2)
        k_tpf = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'get_tpf')
        k_gpf = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'get_property_float' and lname(k, 2) == '21+BASE_PROPERTY_CHARACTER')
        k_spf = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'set_property_float' and lname(k, 1) == PLAYER and lname(k, 2) == '21+BASE_PROPERTY_CHARACTER')
        k_add = find(lambda k: gl.ins[k][1] == 22 and lname(k, 0) == 'mon_timer' and lname(k, 1) == 'fresult')
        k_lt = find(lambda k: gl.ins[k][1] == 36 and lname(k, 0) == 'mon_timer')
        k_clr = find(lambda k: gl.ins[k][1] == 15 and lname(k, 0) == 'mon_timer' and lname(k, 1) == '0.0')
        k_gt = find(lambda k: gl.ins[k][1] == 33 and lname(k, 0) == 'fresult' and lname(k, 1) == '0.0')
        k_res = find(lambda k: gl.ins[k][1] == 32 and lname(k, 1) == 'result')
        k_end = LL['death_000_server_enter@end']
        RES = translate(lwords(k_res))[3+5:3+10]                 # operand 'result' (entity id from get_character_in_box_id)
        FRES = translate(lwords(k_add))[3+5:3+10]                # operand 'fresult'
        for n, z in enumerate(zones):
            nm = z['name']
            if z['kind'] == 'tick': continue      # built after all blocks (it runs the waits)
            if z['kind'] in ('end', 'save'):      # only the player triggers these
                k_cmp = find(lambda k: gl.ins[k][1] == 32 and lname(k, 0) == PLAYER and lname(k, 1) == 'result')
                skip = nm + '@skip'
                body = [tl(k_gcb), with_ops(k_cmp, a2=lab(skip))]
                if z['kind'] == 'end':
                    k_eol = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'end_of_level')
                    body.append(with_ops(k_eol, a1=iconst(int(z.get('next', 0)))))
                else:
                    k_cs = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'can_save')
                    k_as = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'autosave')
                    k_c1 = find(lambda k: gl.ins[k][1] == 32 and lname(k, 0) == 'result' and lname(k, 1) == '1')
                    body += [tl(k_cs), with_ops(k_c1, a2=lab(skip)), tl(k_as)]
                body += [tl(k_end - 1), tl(k_end)]
                zfun.append((nm + '_server_enter', body, {skip: len(body) - 2}))
            elif z['kind'] == 'weather':        # like the campaign's snow/rain/sky boxes: <box>_client_enter / _client_exit functions that only change the atmosphere or sky
                for phase, fname in (('enter', '_client_enter'), ('exit', '_client_exit')):
                    calls = []
                    if z.get(phase + '_atmosphere'): calls.append(call('set_atmosphere', sconst(z[phase + '_atmosphere'])))
                    if z.get(phase + '_sky'): calls.append(call('set_sky', sconst(z[phase + '_sky']), iconst(1)))
                    if calls: zfun.append((nm + fname, calls + [tl(k_end - 1), tl(k_end)], {}))
            elif z['kind'] == 'script':         # commands from the map's .script file, run when the player enters (<name>_server_enter) or leaves (<name>_server_exit) the zone
                inner_extra = {}
                if z.get('leave_cmds'):
                    k_cmpl = find(lambda k: gl.ins[k][1] == 32 and lname(k, 0) == PLAYER and lname(k, 1) == 'result')
                    lskip = nm + '@lskip'
                    lbody = [tl(k_gcb), with_ops(k_cmpl, a2=lab(lskip))]
                    lins, linner = emit(z['leave_cmds'], nm + '@leave')
                    lextra = {}
                    for lbl, off in linner.items(): lextra[lbl] = len(lbody) + off
                    lbody += lins + [tl(k_end - 1), tl(k_end)]
                    zfun.append((nm + '_server_exit', lbody, {lskip: len(lbody) - 2, **lextra}))
                if not z.get('cmds'): continue
                k_cmp = find(lambda k: gl.ins[k][1] == 32 and lname(k, 0) == PLAYER and lname(k, 1) == 'result')
                skip = nm + '@skip'
                body = [tl(k_gcb), with_ops(k_cmp, a2=lab(skip))]
                if z.get('once'):
                    fl = 'script_once_%d' % (n + 1); full = 'gel::' + fl
                    if full not in mnames:
                        src = lrec['gel::bombedone1']; oldlen = struct.unpack_from('<I', src, 0)[0]; nb = full.encode() + b'\0'
                        mnames.append(full); mvar.append((full, struct.pack('<I', len(nb)) + nb + src[4+oldlen:]))
                    t = NBUILTIN + mnames.index(full)
                    FL = [gm.string(fl), t, 1, struct.unpack('<I', struct.pack('<f', float(t)))[0], 0]
                    body += [with_ops(K_FLAGC, a0=FL, a2=lab(skip)), with_ops(K_FLAGS, a0=FL)]
                cins, cinner = emit(z['cmds'], nm)
                for lbl, off in cinner.items(): inner_extra[lbl] = len(body) + off
                body += cins
                body += [tl(k_end - 1), tl(k_end)]
                zfun.append((nm + '_server_enter', body, {skip: len(body) - 2, **inner_extra}))
            elif z['kind'] == 'waypoint':       # a patrolling soldier reached this corner: send it to the next one
                skip = nm + '@skip'
                body = [tl(k_gcb), with_ops(k_res, a0=varop(z['soldier']), a2=lab(skip)), reach_ins(varop(z['soldier']), z['goto']),
                        tl(k_end - 1), tl(k_end)]
                zfun.append((nm + '_server_enter', body, {skip: len(body) - 2}))
            elif z['kind'] == 'kill':
                body = [tl(k_gcb), with_ops(k_mort, a1=RES), tl(k_end - 1), tl(k_end)]
                zfun.append((nm + '_server_enter', body, {}))
            else:
                chunk = float(z.get('damage', 10.0)) * float(z.get('interval', 0.5))
                acc = 'zone_acc_%d' % (n + 1); full = 'gel::' + acc
                if full not in mnames:
                    src = lrec['gel::mon_timer']; oldlen = struct.unpack_from('<I', src, 0)[0]; nb = full.encode() + b'\0'
                    mnames.append(full); mvar.append((full, struct.pack('<I', len(nb)) + nb + src[4+oldlen:]))
                t = NBUILTIN + mnames.index(full)
                ACC = [gm.string(acc), t, 1, struct.unpack('<I', struct.pack('<f', float(t)))[0], 0]
                skip = nm + '@skip'
                body = [tl(k_tpf), with_ops(k_add, a0=ACC), with_ops(k_lt, a0=ACC, a1=fconst(z.get('interval', 0.5)), a2=lab(skip)),
                        with_ops(k_clr, a0=ACC), tl(k_gcb), with_ops(k_gpf, a1=RES), with_ops(k_add, a0=FRES, a1=fconst(-chunk)),
                        with_ops(k_spf, a1=RES, a3=FRES), with_ops(k_gt, a2=lab(skip)), with_ops(k_mort, a1=RES),
                        tl(k_end - 1), tl(k_end)]
                zfun.append((nm + '_server_stay', body, {skip: len(body) - 2}))
    for n, b in enumerate(buttons):     # <name>_server: what happens when the button is used
        nm = b['name']; body = []; inner = {}; skip = nm + '@skip'
        if b.get('once'):
            fl = 'script_once_b%d' % (n + 1); full = 'gel::' + fl
            if full not in mnames:
                src = lrec['gel::bombedone1']; oldlen = struct.unpack_from('<I', src, 0)[0]; nb = full.encode() + b'\0'
                mnames.append(full); mvar.append((full, struct.pack('<I', len(nb)) + nb + src[4+oldlen:]))
            t = NBUILTIN + mnames.index(full)
            FL = [gm.string(fl), t, 1, struct.unpack('<I', struct.pack('<f', float(t)))[0], 0]
            body += [with_ops(K_FLAGC, a0=FL, a2=lab(skip)), with_ops(K_FLAGS, a0=FL)]
        cins, cinner = emit(b['cmds'], nm)
        for lbl, off in cinner.items(): inner[lbl] = len(body) + off
        body += cins
        k_end = LL['death_000_server_enter@end']
        body += [tl(k_end - 1), tl(k_end)]
        inner[skip] = len(body) - 2
        zfun.append((nm + '_server', body, inner))
    if checkpoints:      # load the AI navigation graph (<name>.icp), as the campaign scripts do with cload_checkpoints
        graft.append([0, 55, 2] + [gm.string('cload_checkpoints'), 0xFFFFFFF1, 0xFFFFFFFF, 0xBF800000, 0] + [gm.string(checkpoints), 0xFFFFFFFF, 0, 0, 0])
    for n, e in enumerate(enemies):      # first orders of the soldiers (after the navigation graph is loaded)
        o = e.get('order')
        if not o: continue
        who = varop('id_character_enemy_%02d' % (n + 1))
        if o[0] == 'attack': graft.append(with_ops(K_ATT, a1=who, a2=tl(K_FOL)[3+10:3+15]))
        elif o[0] == 'follow': graft.append(with_ops(K_FOL, a1=who, a3=iconst(o[1])))
        elif o[0] == 'reach': graft.append(reach_ins(who, o[1]))

    # fog and particle effects: clones of the level 1 fog / steam entities (fog: pos, near, far, h1, h2, color; fx: pos, kind, variant, scale, angles)
    def clone_entity(T, nm, over):
        seen = {}
        for k in template_sel(T):
            w = list(lwords(k))
            for j in range(w[2]):
                o = 3 + 5*j
                if w[o] < len(gl.tab) and gl.s(w[o]) == T: w[o:o+5] = [0, 0xFFFFFFFE, 0, 0, 0]
            w = translate(w)
            for j in range(w[2]):
                o = 3 + 5*j
                if w[o+1] == 0xFFFFFFFE: w[o:o+5] = varop(nm)
            if w[1] == 55 and lname(k, 0) in ('load_model', 'load_waveform') and '@file' in over: w[8:13] = sconst(over['@file'])
            if w[1] == 55 and (lname(k, 0) or '').startswith('set_property'):
                p = lname(k, 2)
                if p in over:
                    v = over[p]
                    if isinstance(v, list) and v and v[0] == 'seq':      # the template sets this property several times: one value per occurrence ('' after the list)
                        i = seen.get(p, 0); seen[p] = i + 1; v = v[1][i] if i < len(v[1]) else ''
                    if isinstance(v, list) and v and v[0] == 'ref': w[18:23] = varop(v[1])
                    elif isinstance(v, str): w[18:23] = sconst(v)
                    elif isinstance(v, tuple):
                        for j, x in enumerate(v): w[3+5*(3+j):3+5*(4+j)] = fconst(x)
                    elif isinstance(v, int): w[18:23] = iconst(v)
                    else: w[18:23] = fconst(v)
            graft.append(w)
    for n, e in enumerate(fogs):
        r, g_, b = e['color']
        clone_entity('id_fog_FOG_001', 'id_fog_map_%02d' % (n + 1), {'0+BASE_PROPERTY': 'FOG_MAP_%02d' % (n + 1), '1+BASE_PROPERTY': tuple(e['pos']),
            '0+BASE_PROPERTY_FOG': float(e['near']), '1+BASE_PROPERTY_FOG': float(e['far']), '2+BASE_PROPERTY_FOG': float(e['h1']), '3+BASE_PROPERTY_FOG': float(e['h2']),
            '4+BASE_PROPERTY_FOG': float(r), '5+BASE_PROPERTY_FOG': float(g_), '6+BASE_PROPERTY_FOG': float(b)})
    for n, e in enumerate(drts):     # D.R.T. computers: clones of the lv1 'drt_qg' entity (the engine draws the terminal and plays the movies when the player uses it)
        clone_entity('id_entity_drt_drt_qg', 'id_entity_drt_map_%02d' % (n + 1), {'0+BASE_PROPERTY': 'drt_map_%02d' % (n + 1), '1+BASE_PROPERTY': tuple(e['pos']),
            '0+BASE_PROPERTY_EDRT': (0.0, 0.0, float(e['yaw'])), '4+BASE_PROPERTY_EDRT': float(e.get('time', 3000.0)),
            '3+BASE_PROPERTY_EDRT': ['seq', ['movies\\' + m for m in e['movies']]]})
    for n, e in enumerate(turrets):  # automatic machine-gun turrets: clones of the lv1 'AUTO_MG_001' (the engine draws auto_mg.4x3); property 0 = active
        clone_entity('id_auto_mg_AUTO_MG_001', 'id_auto_mg_map_%02d' % (n + 1), {'0+BASE_PROPERTY': 'AUTO_MG_MAP_%02d' % (n + 1), '1+BASE_PROPERTY': tuple(e['pos']),
            '0+BASE_PROPERTY_AUTO_MG': 0,     # switched on at run time by the clock (like the campaign's alarm script); the game ignores it while creating
            '10+BASE_PROPERTY_AUTO_MG': float(e['yaw']),
            '2+BASE_PROPERTY_AUTO_MG': float(e.get('yaw_min', -90.0)), '3+BASE_PROPERTY_AUTO_MG': float(e.get('yaw_max', 90.0)),
            '1+BASE_PROPERTY_AUTO_MG': float(e.get('rate', 0.1)), '11+BASE_PROPERTY_AUTO_MG': float(e.get('health', 1000.0)),
            '9+BASE_PROPERTY_AUTO_MG': 1 if e.get('friendly') else 2})     # 9 = team: 1 = the player's side (level 1's turrets), 2 = enemy
    waves = {}
    for n, e in enumerate(sounds):  # ambient sounds and music: clones of the lv1 'alarme_qg' sound and its waveform with another .wav
        f = e['file'].lower()
        if f not in waves:
            waves[f] = 'id_waveform_snd_%02d' % (len(waves) + 1)
            clone_entity('id_waveform_alarme_qg', waves[f], {'@file': e['file']})
        clone_entity('id_sound_alarme_qg', e['var'], {'0+BASE_PROPERTY': e['var'][3:], '1+BASE_PROPERTY': tuple(e['pos'] or start),
            '1+BASE_PROPERTY_SOUND': ['ref', waves[f]], '2+BASE_PROPERTY_SOUND': float(e['volume']), '3+BASE_PROPERTY_SOUND': float(e['near']),
            '4+BASE_PROPERTY_SOUND': float(e['far']), '6+BASE_PROPERTY_SOUND': int(e['loop']), '7+BASE_PROPERTY_SOUND': 1 if e['on'] else 0})
    if alarm:       # alarm sirens (the lv1 'alarme_qg' sound, off until 'alarm on'): one at each turret, or at the player start
        clone_entity('id_waveform_alarme_qg', 'id_waveform_alarm_map', {})
        for n, p in enumerate([t['pos'] for t in turrets] or [start]):
            clone_entity('id_sound_alarme_qg', 'id_sound_alarm_map_%02d' % (n + 1), {'0+BASE_PROPERTY': 'alarm_map_%02d' % (n + 1), '1+BASE_PROPERTY': tuple(p),
                '1+BASE_PROPERTY_SOUND': ['ref', 'id_waveform_alarm_map'], '7+BASE_PROPERTY_SOUND': 0})
    for n, e in enumerate(dogs):     # dogs: clones of the lv1 'DOG_001'. From Game.exe: 5 = team (attacks characters of other teams), 7 = explodes on attack
        # (radius 200, damage 50, the dog is removed), 8 = alternate skin (crashes without the campaign's textures, so it is not set)
        nm = 'id_dog_map_%02d' % (n + 1); boom = bool(e.get('explosive'))
        clone_entity('id_dog_DOG_001', nm, {'0+BASE_PROPERTY': 'DOG_MAP_%02d' % (n + 1), '1+BASE_PROPERTY': tuple(e['pos']),
            '0+BASE_PROPERTY_DOG': float(e['yaw']), '1+BASE_PROPERTY_DOG': float(e.get('range', 200.0)),
            '2+BASE_PROPERTY_DOG': float(e.get('health', 50.0)), '3+BASE_PROPERTY_DOG': float(e.get('damage', 20.0)),
            '5+BASE_PROPERTY_DOG': 1 if e.get('friendly') else 2, '6+BASE_PROPERTY_DOG': 1, '7+BASE_PROPERTY_DOG': 1 if boom else 0})
    HELI_FILES = {'allies': 'helico_transporter_allies.4x3', 'enemy': 'helico_transporter_ennemi.4x3'}
    if helis:    # helicopters: the instructions of lv1's create_heli function (create_entity 3, model, name, position, flag 12, start)
        hb = LL['create_heli']
        assert [lname(hb + o, 0) for o in (8, 11, 13, 14, 15, 17, 18)] == ['create_entity', 'load_model', 'set_property_int', 'set_property_string', 'set_property_vector', 'set_property_int', 'start_entity'], 'create_heli layout'
        hmodel = {}
        for n, e in enumerate(helis):
            nm = 'id_helico_map_%02d' % (n + 1); mf = HELI_FILES[e['kind']]
            if mf not in hmodel:
                hmodel[mf] = 'id_helico_model_map_%d' % (len(hmodel) + 1)
                graft += [translate(lwords(hb + 11)), None]
                graft[-2][8:13] = sconst(mf); graft[-1] = translate(lwords(hb + 12)); graft[-1][3:8] = varop(hmodel[mf])
            graft.append(translate(lwords(hb + 8)))
            b = translate(lwords(hb + 9)); b[3:8] = varop(nm); graft.append(b)
            for o, patch in ((13, dict(a1=varop(nm), a3=varop(hmodel[mf]))), (14, dict(a1=varop(nm), a3=sconst(e['name']))),
                             (15, dict(a1=varop(nm), a3=fconst(e['pos'][0]), a4=fconst(e['pos'][1]), a5=fconst(e['pos'][2]))), (17, dict(a1=varop(nm)))):
                w = translate(lwords(hb + o))
                for j, op in patch.items(): w[3+5*int(j[1:]):8+5*int(j[1:])] = op
                graft.append(w)
            for pr, val in (('17', 800.0), ('18', 1800.0), ('21', 0.1), ('16', 0.5)):      # sound ranges, as the campaign sets them before starting its helicopters
                kk = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'set_property_float' and lname(k, 2) == pr + '+BASE_PROPERTY_HELICOPTER')
                graft.append(with_ops(kk, a1=varop(nm), a3=fconst(val)))
            graft.append(call('start_entity', varop(nm)))
    MG_KINDS = {     # mounted guns of the campaign: model, arc (pitch range, 0, yaw range), property 3, weapon (4), seconds between shots (5)
        'bunker': ('FMG_mitrailleuse_bunker.4x3', (90.0, 0.0, 90.0), 1, 8, 0.1), 'handles': ('FMG_poignees.4x3', (90.0, 0.0, 80.0), 1, 8, 0.1),
        'launcher': ('FMG_launcher_sans_pied.4x3', (75.0, 0.0, 75.0), 1, 7, 0.5), 'launcher_stand': ('FMG_launcher_avec_pied.4x3', (90.0, 0.0, 55.0), 1, 7, 0.5),
        'desk': ('FMG_pupitre.4x3', (50.0, 0.0, 80.0), 1, 5, 0.09)}
    mgmodel = {}
    for n, e in enumerate(mguns):    # mounted guns the player can use: clones of the lv1 'FIXED_GUN_001', one loaded model per kind
        mf, arc, p3, wpn, rate = MG_KINDS.get(e.get('kind', 'bunker'), MG_KINDS['bunker'])
        if mf not in mgmodel:
            mgmodel[mf] = 'id_model_fixed_gun_map_%d' % (len(mgmodel) + 1)
            clone_entity('id_model_fixed_gun_bunker', mgmodel[mf], {'@file': 'models\\' + mf})
        if e.get('arc'): arc = tuple(e['arc'])
        clone_entity('id_fixedgun_FIXED_GUN_001', 'id_fixedgun_map_%02d' % (n + 1), {'0+BASE_PROPERTY': 'FIXED_GUN_MAP_%02d' % (n + 1), '1+BASE_PROPERTY': tuple(e['pos']),
            '0+BASE_PROPERTY_FIXED_GUN': ['ref', mgmodel[mf]], '1+BASE_PROPERTY_FIXED_GUN': (0.0, 0.0, float(e['yaw'])), '2+BASE_PROPERTY_FIXED_GUN': arc,
            '3+BASE_PROPERTY_FIXED_GUN': p3, '4+BASE_PROPERTY_FIXED_GUN': wpn, '5+BASE_PROPERTY_FIXED_GUN': float(rate)})
    for n, e in enumerate(docs):     # readable documents: clones of the lv1 'DOC_drt' entity (text = a Trad.ibf text id such as XX1DOCU002)
        clone_entity('id_entity_document_DOC_drt', 'id_entity_document_map_%02d' % (n + 1), {'0+BASE_PROPERTY': 'DOC_MAP_%02d' % (n + 1), '1+BASE_PROPERTY': tuple(e['pos']),
            '0+BASE_PROPERTY_DOCUMENT': (0.0, 0.0, float(e['yaw'])), '3+BASE_PROPERTY_DOCUMENT': e['text']})
    for n, e in enumerate(fx):
        nm = 'id_predef_fx_map_%02d' % (n + 1)
        clone_entity('id_predef_fx_vapor', nm, {'0+BASE_PROPERTY': 'fx_map_%02d' % (n + 1), '1+BASE_PROPERTY': tuple(e['pos']),
            '0+BASE_PROPERTY_PREDEF_FX': int(e['kind']), '1+BASE_PROPERTY_PREDEF_FX': int(e['variant']),
            '2+BASE_PROPERTY_PREDEF_FX': float(e['scale']), '3+BASE_PROPERTY_PREDEF_FX': float(e['scale']),
            '42+BASE_PROPERTY_PARTICLE_GENERATOR': tuple(e['angles'])})
        graft.append(call('start_entity', varop(nm)))
    # static meshes: a stock model placed as a 'mover' entity (clone of a level 1 mover) plus one loaded-model entity per distinct model file
    MODEL_T, MOVER_T = 'id_model__DOOR_porte_blindee_model', 'id_mover_boiteD_001'
    loaded = {}
    for n, e in enumerate(props):
        mf = e['model']
        if mf not in loaded:
            loaded[mf] = 'id_model_prop_%02d' % (len(loaded) + 1)
            clone_entity(MODEL_T, loaded[mf], {'@file': mf, '0+BASE_PROPERTY': mf.rsplit('.', 1)[0] + '_prop'})
        nm = 'id_mover_prop_%02d' % (n + 1)
        over = {'0+BASE_PROPERTY': 'prop_%02d' % (n + 1), '1+BASE_PROPERTY': tuple(e['pos']), '21+BASE_PROPERTY_MOVER': tuple(e['angles']),
                '0+BASE_PROPERTY_MOVER': ['ref', loaded[mf]], '1+BASE_PROPERTY_MOVER': e.get('node', '')}
        if e.get('mode', 'static') == 'static':     # not destructible (values of the campaign's electric pole mover)
            over.update({'3+BASE_PROPERTY_MOVER': 1, '10+BASE_PROPERTY_MOVER': 1, '13+BASE_PROPERTY_MOVER': 999999.0, '14+BASE_PROPERTY_MOVER': 0, '15+BASE_PROPERTY_MOVER': 100.0,
                         '16+BASE_PROPERTY_MOVER': 2, '22+BASE_PROPERTY_MOVER': -1, '25+BASE_PROPERTY_MOVER': 0, '23+BASE_PROPERTY_MOVER': 0.0, '24+BASE_PROPERTY_MOVER': 0.0})
        elif e['mode'] in BREAK_PRESETS:    # (material 16, debris 22, debris count 25, health 15) as the campaign sets them for crates, vents and planks
            m16, m22, m25, m15 = BREAK_PRESETS[e['mode']]
            over.update({'3+BASE_PROPERTY_MOVER': 0, '4+BASE_PROPERTY_MOVER': 0, '10+BASE_PROPERTY_MOVER': 0, '13+BASE_PROPERTY_MOVER': 0.0, '14+BASE_PROPERTY_MOVER': 1,
                         '15+BASE_PROPERTY_MOVER': m15, '16+BASE_PROPERTY_MOVER': m16, '22+BASE_PROPERTY_MOVER': m22, '25+BASE_PROPERTY_MOVER': m25,
                         '23+BASE_PROPERTY_MOVER': 1.0, '24+BASE_PROPERTY_MOVER': 0.0})
        clone_entity(MOVER_T, nm, over)
    for n, e in enumerate(waters):     # water: the engine's WATER entity (clone of lv1's WATER_001) + its model (a flat grid with Layer1_0/Layer1_1 nodes whose vertices the engine ripples)
        mv = 'id_model_water_%02d' % (n + 1); nm = 'id_water_map_%02d' % (n + 1)
        clone_entity(MODEL_T, mv, {'@file': e['file'], '0+BASE_PROPERTY': 'water_map_%02d_model' % (n + 1)})
        clone_entity('id_water_WATER_001', nm, {'0+BASE_PROPERTY': 'WATER_MAP_%02d' % (n + 1), '1+BASE_PROPERTY': tuple(e['pos']),
            '1+BASE_PROPERTY_WATER': ['ref', mv], '2+BASE_PROPERTY_WATER': float(e['speed']), '3+BASE_PROPERTY_WATER': 'water_map_%02d' % (n + 1),
            '4+BASE_PROPERTY_WATER': tuple(float(x) for x in e['tint']), '5+BASE_PROPERTY_WATER': float(e['depth']), '6+BASE_PROPERTY_WATER': float(e['height'])})
    for n, cmds in enumerate(starts):    # 'on start' blocks of the script file
        cins, cinner = emit(cmds, 'start%d' % n)
        if cinner: raise ValueError("'save' cannot be used in an 'on start' block")
        graft += cins
    held = {}
    for n, e in enumerate(items):
        if e.get('hold'): held.setdefault(e['hold'], []).append('id_item_pickup_%02d' % (n + 1))
    tur_on = [n for n, e in enumerate(turrets) if e.get('active', True)]
    if waits or deaths or fx or len(fogs) > 1 or held or tur_on:     # clock_server_stay: every frame (player in the map-sized box) advance the running timers
        k_cmpp = find(lambda k: gl.ins[k][1] == 32 and lname(k, 0) == PLAYER and lname(k, 1) == 'result')
        k_end = LL['death_000_server_enter@end']
        body = [tl(k_gcb), with_ops(k_cmpp, a2=lab('clock@end'))]; inner = {}
        if len(fogs) > 1:       # with several fogs only the first one starts on; like the campaign, set the on/off switches at run time (once), not while the level is being created
            FLI = newvar('script_fog_init', 'bombedone1'); fskip = 'foginit@skip'
            body.append(with_ops(K_FLAGC, a0=FLI, a2=lab(fskip)))
            for fi in range(len(fogs)): body.append(call('set_property_int', varop('id_fog_map_%02d' % (fi + 1)), pconst('7+BASE_PROPERTY_FOG', 0x887), iconst(1 if fi == 0 else 0)))
            body.append(with_ops(K_FLAGS, a0=FLI)); inner[fskip] = len(body)
        j = 0
        while j < len(waits):           # emit() may add more waits while we go (a block with several waits)
            k, secs, rest, base = waits[j]; FL, ACC = waitvars(k); skip = base + '@skip'
            body += [with_ops(K_FLAGC, a0=FL, a1=iconst(1), a2=lab(skip)), tl(k_tpf), with_ops(k_add, a0=ACC),
                     with_ops(k_lt, a0=ACC, a1=fconst(secs), a2=lab(skip)), with_ops(K_FLAGS, a0=FL, a1=iconst(0))]
            cins, cinner = emit(rest, base)
            for lbl, off in cinner.items(): inner[lbl] = len(body) + off
            body += cins; inner[skip] = len(body); j += 1
        for dn, (chars, cmds) in enumerate(deaths):     # 'on dead': once all listed characters have health <= 0
            FL = newvar('script_dead_%d' % (dn + 1), 'bombedone1'); skip = 'dead%d@skip' % (dn + 1)
            body.append(with_ops(K_FLAGC, a0=FL, a2=lab(skip)))            # already done -> skip
            for c in chars: body += [with_ops(k_gpf, a1=varop(c)), with_ops(k_gt, a2=lab(skip))]
            body.append(with_ops(K_FLAGS, a0=FL))
            cins, cinner = emit(cmds, 'dead%d' % (dn + 1))
            for lbl, off in cinner.items(): inner[lbl] = len(body) + off
            body += cins; inner[skip] = len(body)
            while j < len(waits):       # waits started inside this block (checked every frame, outside the skip)
                k, secs, rest, base = waits[j]; FL2, ACC = waitvars(k); skip2 = base + '@skip'
                body += [with_ops(K_FLAGC, a0=FL2, a1=iconst(1), a2=lab(skip2)), tl(k_tpf), with_ops(k_add, a0=ACC),
                         with_ops(k_lt, a0=ACC, a1=fconst(secs), a2=lab(skip2)), with_ops(K_FLAGS, a0=FL2, a1=iconst(0))]
                cins, cinner = emit(rest, base)
                for lbl, off in cinner.items(): inner[lbl] = len(body) + off
                body += cins; inner[skip2] = len(body); j += 1
        if tur_on:  # turrets: switch on once the level runs (property 0 = 1), as the campaign's alarm script does
            k_amg = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'set_property_int' and lname(k, 2) == '0+BASE_PROPERTY_AUTO_MG' and lname(k, 3) == '1')
            TFL = newvar('script_turret_init', 'bombedone1'); tskip = 'turinit@skip'
            body.append(with_ops(K_FLAGC, a0=TFL, a2=lab(tskip)))
            for n in tur_on: body.append(with_ops(k_amg, a1=varop('id_auto_mg_map_%02d' % (n + 1))))
            body.append(with_ops(K_FLAGS, a0=TFL)); inner[tskip] = len(body)
        if held:    # breakable props' contents: like the campaign scripts, read the mover's health (15+BASE_PROPERTY_MOVER) and start the pickups once it is 0
            k_mh = find(lambda k: gl.ins[k][1] == 55 and (lname(k, 0) or '').startswith('set_property') and lname(k, 2) == '15+BASE_PROPERTY_MOVER')
            MH = tl(k_mh)[13:18]
            for hp, names in sorted(held.items()):
                FL = newvar('script_drop_%d' % hp, 'bombedone1'); skip = 'drop%d@skip' % hp
                body += [with_ops(K_FLAGC, a0=FL, a2=lab(skip)), with_ops(k_gpf, a1=varop('id_mover_prop_%02d' % hp), a2=MH), with_ops(k_gt, a2=lab(skip)),
                         with_ops(K_FLAGS, a0=FL)] + [call('start_entity', varop(nm)) for nm in names]
                inner[skip] = len(body)
        if fx:      # particle effects end by themselves; like the campaign, start them again whenever they are not running
            k_g47 = find(lambda k: gl.ins[k][1] == 55 and lname(k, 0) == 'get_property_int' and lname(k, 2) == '47+BASE_PROPERTY_PARTICLE_GENERATOR')
            for n in range(len(fx)):
                who = varop('id_predef_fx_map_%02d' % (n + 1)); skip = 'fxrun%d@skip' % (n + 1)
                body += [with_ops(k_g47, a1=who), with_ops(k_g47 + 1, a2=lab(skip)), call('start_entity', who)]
                inner[skip] = len(body)
        inner['clock@end'] = len(body)
        body += [tl(k_end - 1), tl(k_end)]
        zfun.append(('clock_server_stay', body, inner))
    # layout: MP create_entity_editor body, graft, MP rest (return of create_entity_editor .. last function), arrival, MP final op
    cut = ML['create_entity_editor@end'] - 1          # the 'return 0' of create_entity_editor
    nmp = len(gm.ins)
    last = nmp - 1 if gm.ins[-1][1] == 8 else nmp
    newins = [mwords(k) for k in range(cut)] + graft + [mwords(k) for k in range(cut, last)]
    labels = [(o if o < cut else o + len(graft), n) for o, n in mlab]
    a, b = LL['server_new_player_arrival'], LL['server_new_player_arrival@end']
    base = len(newins)
    if with_arrival:
        for k in range(a, b + 1): newins.append(translate(lwords(k)))
        for o, n in llab:
            if a <= o <= b: labels.append((base + o - a, n))
    for fname, body, inner in zfun:
        b0 = len(newins); newins += body
        labels.append((b0, fname)); labels.append((b0 + len(body) - 1, fname + '@end'))
        labels += [(b0 + o, n) for n, o in inner.items()]
    if last < nmp: newins.append(mwords(last))
    labels.sort(key=lambda t: t[0])
    LN = {n: o for o, n in labels}
    for w in newins:
        for j in range(w[2]):
            o = 3 + 5*j
            if w[o+1] == 0xFFFFFFFC:
                t = LN[gm.s(w[o])]; w[o+2] = t; w[o+3] = struct.unpack('<I', struct.pack('<f', float(t)))[0]

    kwd = [x for w in newins for x in w]
    labe = b''.join(struct.pack('<II', o, len(n) + 1) + n.encode() + b'\0' for o, n in labels)
    tab = bytes(gm.tab) + b'\0' * ((-len(gm.tab)) % 4)
    rep = {b'KYWD': struct.pack('<%dI' % len(kwd), *kwd), b'NKWD': struct.pack('<I', len(newins)),
           b'LABE': labe, b'NLAB': struct.pack('<I', len(labels)),
           b'KYWT': tab, b'NKWT': struct.pack('<I', len(gm.tab)),
           b'VARB': b''.join(r for _, r in mvar), b'NVAR': struct.pack('<I', len(mvar))}
    out = bytearray(mp[:8]); delta = 0
    for t, p in mch:
        if t in rep: delta += len(rep[t]) - len(p); p = rep[t]
        out += t + struct.pack('<I', len(p) + 8) + p
    struct.pack_into('<I', out, 4, struct.unpack_from('<I', mp, 4)[0] + delta)
    out += mp[mend:]
    return bytes(out), len(newins)
