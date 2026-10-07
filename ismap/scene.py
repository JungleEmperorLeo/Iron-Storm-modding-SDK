"""Build an Iron Storm .4x3 scene (one world sector holding one room sector) from triangles.

Rules learned from the stock maps (see FINDINGS.md):
- render 'data' groups are non-indexed triangle lists (tree type 3) of <= 54 vertices
- STGM 'text' = list of distinct texture ids; 'comd' is a command list:
  (0,0)(0,0) then per group: set texture (41, or 1 for the last) + draw group (23, or 3 for the last)
- visible side of a triangle: cross(v1-v0, v2-v0) points along the stored normal
- collision faces (CSTC) use the same winding, plane normal pointing into free space
- every sector's cust/BUI1 byte must be 1
"""
import math, struct
from .repack import write_map
from .texio import encode_dxt1, encode_dxt5

P = struct.pack
def chunk(cid, data): return cid + P('<I', len(data)) + data + (b'\0' if len(data) & 1 else b'')
def lst(form, *kids): return chunk(b'LIST', form + b''.join(kids))
def nam(s): return chunk(b'@nam', s.encode('latin1') + b'\0')
def f4(*v): return P('<%df' % len(v), *v)
def u4(*v): return P('<%dI' % len(v), *v)
def defid(i): return chunk(b'def!', u4(i))

MAX_GROUP_VERTS = 54
HEAD = [(b'4X.v', bytes.fromhex('080001000500c20424666e782e76657200312e382e313231382e3500000000000000000000000000')),
        (b'@nam', b'4X Studio Builder Generated Scene\x00'),
        (b'Aupm', f4(1.0))]
CUST = lst(b'cust', lst(b'BUI\xb1', chunk(b'BUI1', b'\x01')))

def sphere(pts):
    c = [(min(p[i] for p in pts) + max(p[i] for p in pts)) / 2 for i in range(3)]
    return c, max(math.dist(c, p) for p in pts) * 1.0001 + 0.01

def bsp_root(mn, mx):
    """600-byte BSP 'root' block: 25 x [nx,ny,nz,d,u32,u32]; inward AABB planes (n.p + d >= 0)."""
    planes = [((0, -1, 0), mx[1]), ((1, 0, 0), -mn[0]), ((0, 1, 0), -mn[1]),
              ((0, 0, -1), mx[2]), ((0, 0, 1), -mn[2]), ((-1, 0, 0), mx[0])]
    ent = [None] * 25
    for i, (n, d) in enumerate(planes): ent[i] = f4(*n, d) + u4(0, 3)
    for base, src in ((7, 5), (10, 4), (13, 3), (16, 2), (19, 1), (22, 0)): ent[base] = ent[src]
    for i in range(25):
        if ent[i] is None: ent[i] = f4(0, 0, 0, 0) + u4(1 if (i % 3 == 2 or i == 6) else 2, 0)
    return b''.join(ent)

def texture_record(tex_id, name, img, alpha=False):
    w, h, mips, buf = (encode_dxt5 if alpha else encode_dxt1)(img)
    sizes = []; off = 0; ww, hh = w, h
    for _ in range(mips):
        sz = max(1, (ww + 3) // 4) * max(1, (hh + 3) // 4) * (16 if alpha else 8)
        sizes += [sz, off]; off += sz; ww = max(1, ww // 2); hh = max(1, hh // 2)
    return defid(tex_id) + nam(name) + lst(b'IMAG', nam(name), chunk(b'mip_', u4(*sizes)),
        chunk(b'info', (b'DXT5' if alpha else b'DXT1') + u4(w, h, mips)), chunk(b'bfsz', u4(len(buf))), chunk(b'bufr', buf))

# material kinds a texture can use (see docs/1_MAPPING.md, "Materials"). A kind may carry its own opacity: 'blend@0.7'.
KINDS = ('opaque', 'cut', 'blend', 'blend_tex', 'reflect', 'reflect_bright', 'add')
_RANK = {k: i for i, k in enumerate(KINDS)}      # drawing order: solid first, translucent after, additive glow last

def split_kind(key):
    """'blend@0.7' -> ('blend', 0.7); 'cut' -> ('cut', None)"""
    base, _, op = key.partition('@')
    return base, (float(op) if op else None)

def kind_order(key):
    base, op = split_kind(key)
    return (_RANK[base], op if op is not None else -1.0)

def material_record(mat_id, lit=True, kind='opaque', opacity=0.6):
    kind, own = split_kind(kind)
    if own is not None: opacity = own
    if kind == 'cut':     # alpha-tested (fences, grates, foliage): stock 'GRID_' material, type 0x109 + txbl
        return (defid(mat_id) + nam('GRID_alpha') + chunk(b'$amb', f4(*([0.1] * 3 if lit else [0.59] * 3), 1.0))
                + chunk(b'$dif', f4(0, 0, 0, 0)) + chunk(b'type', u4(0x109)) + chunk(b'txbl', u4(1)))
    if kind == 'blend':   # translucent, still lit (glass, level 2's swamp water 'WATE_flaque_eau'): type 0x111 + constant opacity
        return (defid(mat_id) + nam('GLAS_glass') + chunk(b'$amb', f4(*([0.1] * 3 if lit else [0.59] * 3), 1.0))
                + chunk(b'$dif', f4(0, 0, 0, 0)) + chunk(b'Aopa', f4(opacity)) + chunk(b'type', u4(0x111)))
    if kind == 'blend_tex':   # translucent from the texture's own alpha channel (stock blood splats 'WATE_Giclures_sang': type 0x111 + txbl 1); the texture needs an alpha channel
        return (defid(mat_id) + nam('WATE_alpha') + chunk(b'$amb', f4(*([0.1] * 3 if lit else [0.59] * 3), 1.0))
                + chunk(b'$dif', f4(0, 0, 0, 0)) + chunk(b'type', u4(0x111)) + chunk(b'txbl', u4(1)))
    if kind in ('reflect', 'reflect_bright'):   # translucent with an environment reflection (helicopter window 'environhelico' 0x151, level 6 domes 'GLAS_ref_*' 0x150)
        bright = kind == 'reflect_bright'
        return (defid(mat_id) + nam('GLAS_ref') + chunk(b'$amb', f4(0.182, 0.064, 0.173, 1.0)) + chunk(b'$dif', f4(0, 0, 0, 0))
                + (chunk(b'Asil', f4(1.0)) if bright else b'') + chunk(b'Aopa', f4(opacity)) + chunk(b'type', u4(0x150 if bright else 0x151)))
    if kind == 'add':     # additive glow, ignores lighting (flames, halos, light shafts: stock type 0x110)
        return (defid(mat_id) + nam('ADD_glow') + chunk(b'$amb', f4(0.588, 0.588, 0.588, 1.0)) + chunk(b'$dif', f4(0, 0, 0, 0))
                + chunk(b'Asil', f4(1.0)) + (chunk(b'Aopa', f4(opacity)) if own is not None else b'') + chunk(b'type', u4(0x110)))
    if lit:
        # copy of stock isdm3 world material (def 0x34): ambient 0.1, type 0x101 -> lit by the baked vertex colours
        return (defid(mat_id) + nam('GROU_sol') + chunk(b'$amb', f4(0.1, 0.1, 0.1, 1.0))
                + chunk(b'$dif', f4(0, 0, 0, 0)) + chunk(b'type', u4(0x101)))
    # copy of stock 'Material #108191' (ambient 0.59, type 0x100): full brightness, ignores vertex colours
    return (defid(mat_id) + nam('Material #108191') + chunk(b'$amb', f4(150/255, 150/255, 150/255, 1.0))
            + chunk(b'$dif', f4(0, 0, 0, 0)) + chunk(b'Asil', f4(1.0)) + chunk(b'type', u4(0x100)))

def _has_alpha(img):
    if img.mode != 'RGBA': return False
    lo, hi = img.getchannel('A').getextrema()
    return lo < 250

def tex_kind(name, img, glass_words=('glass',), override=None):
    if override: return override
    if any(w in name.lower() for w in glass_words): return 'blend'
    return 'cut' if _has_alpha(img) else 'opaque'

def _room(rid, name, render_tris, collide_tris, tex_id, tex_ids_local, kinds, used_global, mat_ids, ids, vcolour, colour, surface, box):
    """one sector: (SECT record parts) -> (def id, lst SECT bytes builder args, bounds)"""
    tex_names = sorted({t for t, *_ in render_tris}, key=lambda t: (kind_order(kinds[t]), t))
    used = sorted({kinds[t] for t in tex_names}, key=kind_order)
    lset_id = next(ids); bui_id = next(ids); sec_id = next(ids)
    per = MAX_GROUP_VERTS // 3
    groups = []
    for t in tex_names:
        tris = [r for r in render_tris if r[0] == t]
        for k in range(0, len(tris), per): groups.append((t, tris[k:k + per]))
    datas = []; allpos = []; cmds = []; cur_mat = 0
    for gi, (t, tris) in enumerate(groups):
        pos = [p for _, tri, _, _ in tris for p in tri]
        nrm = [n for _, tri, _, n in tris for _ in tri]
        uvs = [uv for _, _, uv3, _ in tris for uv in uv3]
        n = len(pos)
        vrtx = (u4(0x101f2, n) + b''.join(f4(*p, 1.0) for p in pos)
                + u4(n) + b''.join(f4(*q, 1.0) for q in nrm)
                + u4(n) + b''.join(u4(vcolour(p, q) if vcolour else colour, 0xff000000) for p, q in zip(pos, nrm))
                + u4(n) + b''.join(f4(*uv) for uv in uvs) + b'\0' * 28)
        c, r = sphere(pos); cen = [sum(p[i] for p in pos) / n for i in range(3)]
        datas.append(lst(b'data', chunk(b'tree', u4(3, n << 16, 0) + f4(0, 0, 0, *cen)), chunk(b'sphr', f4(*c, r)),
                         lst(b'VRTX', chunk(b'vrtx', vrtx), chunk(b'bsph', b'\0' * 20)), chunk(b'hsls', u4(0))))
        allpos += pos
        last = gi == len(groups) - 1
        ti = tex_names.index(t)
        gk = used.index(kinds[t])
        if gk != cur_mat: cmds.append((c, r, gk, 0)); cur_mat = gk
        cmds.append((c, r, ti, 1 if last else 41)); cmds.append((c, r, gi, 3 if last else 23))
    c, r = sphere(allpos)
    comd = (f4(*c, r) + u4(0)) * 2 + b''.join(f4(*cc, rr) + u4((i << 16) | fl) for cc, rr, i, fl in cmds)
    stgm = lst(b'STGM', chunk(b'bsph', f4(*c, 1.0, r)), chunk(b'comd', comd), chunk(b'matl', u4(len(used), *[mat_ids[k] for k in used])),
               chunk(b'text', u4(len(tex_names), *[tex_id[t] for t in tex_names])),
               lst(b'LSET', defid(lset_id)), *datas, chunk(b'mxvx', u4(MAX_GROUP_VERTS)))

    # ---- collision
    verts = {}; vlist = []; planes = {}; plist = []; faces = []
    def vi(p):
        k = tuple(round(x, 3) for x in p)
        if k not in verts: verts[k] = len(vlist); vlist.append(k)
        return verts[k]
    surf_ids = []; pg = []
    for item in collide_tris:
        tri, n = item[0], item[1]
        sv = item[2] if len(item) > 2 else surface
        if sv not in surf_ids: surf_ids.append(sv)
        d = -sum(n[i] * tri[0][i] for i in range(3))
        pk = tuple(round(x, 5) for x in (*n, d))
        if pk not in planes: planes[pk] = len(plist); plist.append(pk)
        faces.append((vi(tri[0]), vi(tri[1]), vi(tri[2]), planes[pk])); pg.append(surf_ids.index(sv) + 1)
    nf = len(faces)
    mn = [min(v[i] for v in vlist + [tuple(p) for p in allpos]) for i in range(3)]
    mx = [max(v[i] for v in vlist + [tuple(p) for p in allpos]) for i in range(3)]
    cstc = lst(b'CSTC', chunk(b'vrtx', b''.join(f4(*v, 1.0) for v in vlist)), chunk(b'plan', b''.join(f4(*p) for p in plist)),
               chunk(b'face', b''.join(u4(*f) for f in faces)), chunk(b'pgix', u4(*pg)),
               *[lst(b'BUI\xb2', defid(100000 + rid * 100 + k), chunk(b'BUI2', P('<H', sv))) for k, sv in enumerate(surf_ids)],
               chunk(b'octr', u4(0, nf, 0, 0, 0, 0, 0, 0)), chunk(b'fcix', u4(*range(nf))),
               chunk(b'mnmx', f4(*mn, 1.0, *mx, 1.0)))
    mesh = lst(b'MESH', stgm, nam('static'), cstc, lst(b'LSET'))
    cx = [(mn[i] + mx[i]) / 2 for i in range(3)]; rr = math.dist(mn, mx) / 2 + 1
    bmn, bmx = box if box else ([v - 32 for v in mn], [v + 32 for v in mx])
    head = [defid(sec_id), nam(name), mesh, chunk(b'sphr', f4(*cx, 1.0, rr)),
            lst(b'BSP ', chunk(b'root', bsp_root(bmn, bmx)))]
    return sec_id, head, (mn, mx)

def _portal(quad, normal):
    """PORT chunk: bounding sphere, plane (normal points into the owning sector), 4-vertex hull wound counter-clockwise about the normal"""
    c = [sum(p[i] for p in quad) / 4 for i in range(3)]
    r = max(math.dist(c, p) for p in quad)
    d = -sum(normal[i] * quad[0][i] for i in range(3))
    return lst(b'PORT', chunk(b'sphr', f4(*c, 1.0, r)), chunk(b'plan', f4(*normal, d)),
               chunk(b'hull', b''.join(f4(*p, 1.0) for p in quad)))

def build(render_tris, collide_tris, textures, name='map', colour=0xff808080, vcolour=None, lit=False, surface=3, glass=0.6,
          sectors=None, portals=None, materials=None):
    """render_tris: [(tex_name, (p0,p1,p2), (uv0,uv1,uv2), normal)]   (visible-side winding)
       collide_tris: [((p0,p1,p2), normal)]                           (normal = free side)
       textures: {tex_name: PIL.Image (power of two)}
       sectors: optional [dict(box=(mn,mx), render=[...], collide=[...])] -> one room per entry (boxes must tile without overlap)
       portals: optional [dict(a=i, b=j, quad=[4 points], normal=(nx,ny,nz) pointing into sector a)]
       returns (head, records, tags) for write_map"""
    ids = iter(range(1, 1 << 30))
    if sectors is None: sectors = [dict(box=None, render=render_tris, collide=collide_tris)]
    all_render = [r for s in sectors for r in s['render']]
    kinds = {t: tex_kind(t, textures[t], override=(materials or {}).get(t)) for t in {t for t, *_ in all_render}}
    tex_names = sorted(kinds, key=lambda t: (kind_order(kinds[t]), t))
    tex_id = {t: next(ids) for t in tex_names}
    used = sorted(set(kinds.values()), key=kind_order)
    mat_ids = {k: next(ids) for k in used}
    recs = [texture_record(tex_id[t], t, textures[t], alpha=(split_kind(kinds[t])[0] in ('cut', 'blend_tex'))) for t in tex_names] + [material_record(mat_ids[k], lit, k, glass) for k in used]
    tags = [b'TEXU'] * len(tex_names) + [b'MATL'] * len(used)

    rooms = []
    for i, s in enumerate(sectors):
        if not s['render']: raise SystemExit('map has no visible faces' if len(sectors) == 1 else 'sector %d has no visible faces' % i)
        if not s['collide']: raise SystemExit('map has no solid faces' if len(sectors) == 1 else 'sector %d has no solid faces' % i)
        rname = 'Room_' + name if len(sectors) == 1 else 'Room_%s_%02d' % (name, i)
        rooms.append(_room(i, rname, s['render'], s['collide'], tex_id, None, kinds, used, mat_ids, ids, vcolour, colour, surface, s['box']))
    mn = [min(r[2][0][k] for r in rooms) for k in range(3)]; mx = [max(r[2][1][k] for r in rooms) for k in range(3)]
    cx = [(mn[i] + mx[i]) / 2 for i in range(3)]; rr = math.dist(mn, mx) / 2 + 1

    # ---- portal graph: every sector is embedded once (first SCLK that reaches it), later references are bare ids
    n = len(rooms); nb = [dict() for _ in range(n)]
    for p in portals or []:
        a, b, q, nrm = p['a'], p['b'], p['quad'], p['normal']
        nb[a].setdefault(b, []).append(_portal(q, nrm))
        nb[b].setdefault(a, []).append(_portal(q[::-1], tuple(-x for x in nrm)))
    embedded = set()
    def emit(i):
        embedded.add(i)
        sid, head, _ = rooms[i]
        kids = []
        for j in sorted(nb[i]):
            if j in embedded: tail = chunk(b'SECT', u4(rooms[j][0]))
            else: tail = emit(j)
            kids.append(lst(b'SCLK', *nb[i][j], tail))
        return lst(b'SECT', *head, *kids, CUST)
    top = []; direct = []
    for i in range(n):
        if i not in embedded: top.append(emit(i)); direct.append(i)
    if n == 1:
        world = (nam('Sector_' + name) + chunk(b'sphr', f4(*cx, 1.0, rr * 1.01))
                 + lst(b'BSP ', chunk(b'root', bsp_root([-50000] * 3, [50000] * 3))) + top[0] + CUST)
    else:
        world = (nam('Sector_' + name) + chunk(b'sphr', f4(*cx, 1.0, rr * 1.01))
                 + lst(b'BSP ', chunk(b'root', bsp_root([-50000] * 3, [50000] * 3))) + b''.join(top) + CUST
                 + b''.join(chunk(b'SECT', u4(rooms[i][0])) for i in range(n) if i not in direct))
    recs.append(world); tags.append(b'SECT')
    return HEAD, recs, tags, (mn, mx)

def write(path, head, recs, tags): write_map(path, head, recs, tags)
