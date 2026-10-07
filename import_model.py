"""Import a modelled object (.obj + texture) as a replacement for a stock Iron Storm model.

  python import_model.py smg_first.4x3 mygun.obj --texture mygun.png
  python import_model.py smg_first.4x3 mygun.obj --axes zup --scale 0.05 --no-fit

The result goes to imported_models\\<stock name>; models_install.py puts it into the game. Without --no-fit the object is
scaled and centred to the size of the stock model's mesh, so a gun modelled at any scale lands in the right place."""
import argparse, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from ismap import bigfile, modelswap, objmodel

def stock_bytes(game, name):
    for base in ('Models.ibf.bak', 'Models.ibf'):
        ibf = os.path.join(game, base); lst = os.path.join(game, base.replace('.ibf', '.lst'))
        if os.path.exists(ibf) and os.path.exists(lst):
            d = bigfile.read_file(ibf, lst, name)
            if d: return d
    return None

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stock'); ap.add_argument('obj')
    ap.add_argument('--texture', help='texture (png/tga/jpg) used for every material without its own map_Kd')
    ap.add_argument('--node', help='which mesh node of the stock model to replace (default: the main one)')
    ap.add_argument('--axes', default='yup', choices=sorted(objmodel.AXES), help='yup (default): y up, -z forward, as written by Blender\'s .obj exporter; zup: z up, barrel along -y')
    ap.add_argument('--scale', type=float, default=1.0); ap.add_argument('--offset', default='0,0,0')
    ap.add_argument('--no-fit', action='store_true', help='use --scale/--offset as they are instead of fitting to the stock mesh')
    ap.add_argument('--keep-children', action='store_true', help='keep the stock parts attached to the mesh (magazine, buttons)')
    ap.add_argument('--game', default=os.path.dirname(HERE)); ap.add_argument('--out', default=os.path.join(HERE, 'imported_models'))
    a = ap.parse_args()
    from PIL import Image
    stock = stock_bytes(a.game, a.stock)
    if stock is None: sys.exit('%s not found in %s' % (a.stock, a.game))
    tris, mtl = objmodel.load_obj(a.obj)
    if not tris: sys.exit('no faces in ' + a.obj)
    fit = None if a.no_fit else modelswap.mesh_bbox(stock, a.node)
    tris = objmodel.transform(tris, a.axes, a.scale, tuple(float(x) for x in a.offset.split(',')), fit)
    tex = {}; per = []
    for m, vs in tris:
        f = mtl.get(m) or a.texture
        if not f or not os.path.exists(f): sys.exit('no texture for material %r: give --texture or a map_Kd in the .mtl' % m)
        key = os.path.splitext(os.path.basename(f))[0] + '.tga'
        if key not in tex: tex[key] = modelswap._pot(Image.open(f))
        per.append((key, vs))
    data = modelswap.swap_mesh(stock, per, tex, a.node, a.keep_children)
    os.makedirs(a.out, exist_ok=True); p = os.path.join(a.out, a.stock); open(p, 'wb').write(data)
    print('wrote %s (%d bytes)' % (p, len(data)))
main()
