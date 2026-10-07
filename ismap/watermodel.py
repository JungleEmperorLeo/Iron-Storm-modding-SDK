"""Water surface model for the engine's WATER entity (IS_WATER, Game.exe 0x462750).

The entity does not draw anything itself: it loads a model and looks for nodes named Layer1_0, Layer1_1 (required together),
Layer2_0 + Layer2_1 (optional pair) and Layer3 (optional). Every frame it moves the x/y of each vertex of those nodes in
a circle (radius = speed * 5, phase = (x + y) / extent * 2 pi + clock), so the texture on the surface ripples and
slides. The stock water models (OBJ_WATER_lv4.4x3 ...) are one NODE record: @nam, xfr, then one LIST MESH per layer, drawn
with a type 0x111 material whose texture has an alpha channel (txbl 1).
Vertices are relative to the entity position, and the surface should be a flat grid so the vertices can move."""
import math, struct
from .scene import chunk, lst, nam, f4, u4, defid, HEAD, sphere, texture_record, material_record
import zlib

def _subdivide(tri, uv, step, depth=0):
    """split a triangle (3 positions, 3 uvs) at the midpoint of its longest edge until every edge is <= step"""
    e = [(math.dist(tri[i], tri[(i + 1) % 3]), i) for i in range(3)]
    l, i = max(e)
    if l <= step or depth > 12: return [(tri, uv)]
    j = (i + 1) % 3; k = (i + 2) % 3
    mp = tuple((tri[i][c] + tri[j][c]) / 2 for c in range(3)); mu = tuple((uv[i][c] + uv[j][c]) / 2 for c in range(2))
    a = ((tri[i], mp, tri[k]), (uv[i], mu, uv[k])); b = ((mp, tri[j], tri[k]), (mu, uv[j], uv[k]))
    return _subdivide(*a, step, depth + 1) + _subdivide(*b, step, depth + 1)

def _mesh(name, tris, mat_id, tex_id, lset_id, first):
    """one LIST MESH: tris = [(p0, p1, p2, uv0, uv1, uv2)], vertices shared by (position, uv)"""
    pos, uvs, index, key = [], [], {}, {}
    indx = []
    for p0, p1, p2, u0, u1, u2 in tris:
        indx.append(3)
        for p, uv in ((p0, u0), (p1, u1), (p2, u2)):
            q = (round(p[0], 4), round(p[1], 4), round(p[2], 4)); ku = (round(uv[0], 5), round(uv[1], 5))
            if q not in index: index[q] = len(pos); pos.append(p)
            if (q, ku) not in key: key[(q, ku)] = len(uvs); uvs.append(uv)
            indx.append(index[q] | (key[(q, ku)] << 16))
    n = len(pos); c, r = sphere(pos)
    nrm = [(0.0, 0.0, 1.0)] * n
    vrtx = (u4(0x132, n) + b''.join(f4(*p, 1.0) for p in pos) + u4(n) + b''.join(f4(*q, 1.0) for q in nrm)
            + u4(0, 0, len(uvs)) + b''.join(f4(*uv) for uv in uvs) + b'\0' * 28)      # stock layout after the normals: 0, 0, uv count, uvs, 28 zero bytes
    face = [(0x90, mat_id), (0x80, tex_id), (0x1000, 0x10002), (5, len(tris))]
    prim = lst(b'PRIM', chunk(b'vrtx', vrtx), chunk(b'bsph', f4(*c, 1.0, r)),
               chunk(b'face', b''.join(u4(a, b) for a, b in face)), chunk(b'indx', u4(*indx)))
    xfr = chunk(b'\x11xfr', f4(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1) + u4(0x304))
    lset = lst(b'LSET', defid(lset_id)) if first else chunk(b'LSET', u4(lset_id))
    return lst(b'MESH', prim, nam(name), xfr, lset)

def build(path, tris, tex_name, img, opacity=0.6, step=24.0, layers=2, grid_uv_shift=(0.37, 0.21)):
    """tris: [(p0, p1, p2, uv0, uv1, uv2)] of the water surface, relative to the entity position (z = 0 is the surface).
    Writes the model to path and returns its bytes."""
    img = img.convert('RGBA')
    al = img.split()[3].point(lambda v: int(v * opacity))
    img.putalpha(al)
    pieces = []
    for p0, p1, p2, u0, u1, u2 in tris:
        for tri, uv in _subdivide((p0, p1, p2), (u0, u1, u2), step): pieces.append((*tri, *uv))
    both = pieces + [(a, c, b, ua, uc, ub) for a, b, c, ua, ub, uc in pieces]      # also seen from below
    tex_id, mat_id, lset_id = 1, 2, 3
    texu = texture_record(tex_id, tex_name, img, alpha=True); matl = material_record(mat_id, False, 'blend_tex')
    dx, dy = grid_uv_shift
    second = [(a, b, c, (ua[0] + dx, ua[1] + dy), (ub[0] + dx, ub[1] + dy), (uc[0] + dx, uc[1] + dy)) for a, b, c, ua, ub, uc in both]
    meshes = [_mesh('Layer1_0', both, mat_id, tex_id, lset_id, True), _mesh('Layer1_1', second, mat_id, tex_id, lset_id, False)]
    xfr = chunk(b'\x11xfr', f4(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1) + u4(0x304))
    node = nam('Dummy_water') + xfr + b''.join(meshes)
    # file order of the stock water models: version, TEXU, MATL, name, background colour, scale, NODE (one raw deflate stream over the zip! records)
    head = [(b'4X.v', bytes.fromhex('080001003e00a60124666e782e76657200312e382e3432322e363200000000000000000000000000')), None, None,
            (b'@nam', b'water.max\x00'), (b'$bgc', f4(0, 0, 0, 1.0)), (b'Aupm', f4(10.0)), None]
    zips = iter([(b'TEXU', texu), (b'MATL', matl), (b'NODE', node)])
    co = zlib.compressobj(9, zlib.DEFLATED, -15); body = b''
    for item in head:
        if item is None:
            tag, r = next(zips)
            z = co.compress(r) + co.flush(zlib.Z_SYNC_FLUSH)
            body += chunk(b'zip!', tag + struct.pack('<I', len(r) + 4) + z)
        else: body += chunk(*item)
    out = b'RIFF' + struct.pack('<I', len(body) + 4) + b'SCEN' + body
    open(path, 'wb').write(out)
    return out, len(pieces)
