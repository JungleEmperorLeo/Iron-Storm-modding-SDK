"""Build an Iron Storm object model (.4x3, as used by doors, crates, lifts) from triangles.

Layout learned from the stock models (door_test.4x3, box.4X3, box_collide_stand.4x3) and fnx_core.dll's writer:
  records: TEXU (textures), MATL (one material), MESH:
    LIST PRIM
      vrtx  u32 0x132, n, n x vec4 position, n, n x vec4 normal, 0 (no colours), m, m x (u,v), 28 zero bytes
      bsph  centre xyz, 1.0, radius
      face  command list of (u32 cmd, u32 arg): 0x90 material id, 0x80 texture id, 0x1000 0x10002 (once),
            5 n = draw n counted strips from indx
      indx  u32 entries; a strip is [count, count x (vertex | uv << 16)]
    @nam, \\x11xfr (4x4 identity + u32 0x304)
    LIST CLST  (collision)
      face  per triangle 3 x u16 index into dvtx + u16 pad
      fdta  per triangle 4 planes (nx, ny, nz, d): the face plane, then the outward edge planes v0v1, v1v2, v2v0
      sphr  centre xyz, 1.0, radius
      dvtx  vec4 per triangle corner
    LIST LSET (empty)
Visible side: cross(v1 - v0, v2 - v0) points along the normal (same as the level geometry)."""
import math, struct
from .scene import chunk, lst, nam, f4, u4, defid, HEAD, sphere, texture_record, material_record, tex_kind

def _norm(v):
    l = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / l for x in v]

def _cross(a, b): return [a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0]]

def build(render_tris, collide_tris, textures, name='door', lit=False):
    """render_tris: [(tex_name, (p0,p1,p2), (uv0,uv1,uv2), normal)], collide_tris: [((p0,p1,p2), normal, ...)]
    (coordinates relative to the model origin, game units). Returns (head, records, tags)."""
    tex_names = sorted({t for t, *_ in render_tris})
    ids = iter(range(1, 1 << 20))
    tex_id = {t: next(ids) for t in tex_names}
    mat_id = next(ids)
    recs = [texture_record(tex_id[t], t, textures[t], alpha=(tex_kind(t, textures[t]) == 'cut')) for t in tex_names]
    recs.append(material_record(mat_id, lit, 'opaque')); tags = [b'TEXU'] * len(tex_names) + [b'MATL']

    pos, nrm, uvs, indx = [], [], [], []
    face = [(0x90, mat_id)]
    first = True
    for t in tex_names:
        tris = [r for r in render_tris if r[0] == t]
        face.append((0x80, tex_id[t]))
        if first: face.append((0x1000, 0x10002)); first = False
        for _, tri, uv3, n in tris:
            indx.append(3)
            for p, uv in zip(tri, uv3):
                k = len(pos); pos.append(p); nrm.append(n); uvs.append(uv)
                indx.append(k | (k << 16))
        face.append((5, len(tris)))
    n = len(pos)
    c, r = sphere(pos)
    vrtx = (u4(0x132, n) + b''.join(f4(*p, 1.0) for p in pos) + u4(n) + b''.join(f4(*q, 1.0) for q in nrm)
            + u4(0) + u4(n) + b''.join(f4(*uv) for uv in uvs) + b'\0' * 28)
    prim = lst(b'PRIM', chunk(b'vrtx', vrtx), chunk(b'bsph', f4(*c, 1.0, r)),
               chunk(b'face', b''.join(u4(a, b) for a, b in face)), chunk(b'indx', u4(*indx)))

    dv, cf, fd = [], [], []
    for item in collide_tris:
        tri, nn = item[0], _norm(item[1])
        k = len(dv); dv += list(tri)
        cf.append(struct.pack('<4H', k, k + 1, k + 2, 0))
        planes = [(nn, -sum(nn[i] * tri[0][i] for i in range(3)))]
        for a, b in ((0, 1), (1, 2), (2, 0)):
            e = [tri[b][i] - tri[a][i] for i in range(3)]
            en = _norm(_cross(e, nn))                      # outward for a triangle wound counter-clockwise about nn
            planes.append((en, -sum(en[i] * tri[a][i] for i in range(3))))
        fd.append(b''.join(f4(*pn, d) for pn, d in planes))
    cc, cr = sphere(dv)
    clst = lst(b'CLST', chunk(b'face', b''.join(cf)), chunk(b'fdta', b''.join(fd)), chunk(b'sphr', f4(*cc, 1.0, cr)),
               chunk(b'dvtx', b''.join(f4(*p, 1.0) for p in dv)))
    xfr = chunk(b'\x11xfr', f4(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1) + u4(0x304))
    recs.append(prim + nam(name) + xfr + clst + lst(b'LSET')); tags.append(b'MESH')
    return HEAD, recs, tags
