#!/usr/bin/env python3
"""Export the stock textures from Models.ibf as PNGs for TrenchBroom.

usage: python extract_textures.py GAME_DIR [--only isdm3 isdm1 ...] [--out DIR]
Default output: modtools\\trenchbroom\\textures\\<source file>\\<texture>.png
Each texture is written once (first file that contains it wins)."""
import os, sys, struct, argparse
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from ismap import bigfile
from ismap.repack import read_map_bytes
from ismap.p4x3 import chunks
from ismap.texio import decode

def textures_in(data):
    head, recs, tags, _ = read_map_bytes(data)
    for rec, tag in zip(recs, tags):
        if tag != b'TEXU': continue
        name = None; info = None; buf = None
        def walk(o, e):
            nonlocal name, info, buf
            for cid, po, sz, bad in chunks(rec, o, e):
                if cid == b'@nam' and name is None: name = rec[po:po+sz].split(b'\0')[0].decode('latin1')
                elif cid == b'info': info = (rec[po:po+4].decode('latin1'),) + struct.unpack_from('<3I', rec, po+4)
                elif cid == b'bufr': buf = rec[po:po+sz]
                elif cid == b'LIST': walk(po+4, po+sz)
        walk(0, len(rec))
        if name and info and buf: yield name, info, buf

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('game', nargs='?', default=os.path.dirname(HERE)); ap.add_argument('--only', nargs='*'); ap.add_argument('--out')
    a = ap.parse_args()
    out = a.out or os.path.join(HERE, 'trenchbroom', 'textures')
    ibf, lst = os.path.join(a.game, 'Models.ibf'), os.path.join(a.game, 'Models.lst')
    recs = bigfile.read_lst(lst); seen = set(); total = 0
    with open(ibf, 'rb') as f:
        for name, off, size, _ in recs:
            low = name.lower()
            if not low.endswith('.4x3') or '_light' in low or '_event' in low: continue
            stem = os.path.splitext(os.path.basename(name))[0].lower()
            if a.only and stem not in [x.lower() for x in a.only]: continue
            f.seek(off); data = f.read(size)
            if data[:4] != b'RIFF' or data[8:12] != b'SCEN': continue
            try: texs = list(textures_in(data))
            except Exception as e: print('skip', name, e); continue
            n = 0
            for tname, (fmt, w, h, mips), buf in texs:
                base = os.path.splitext(tname)[0].replace(' ', '_').replace(',', '_')
                if base.lower() in seen: continue
                try: im = decode(fmt, w, h, mips, buf)
                except Exception as e: print('  cannot decode', tname, fmt, e); continue
                seen.add(base.lower())
                d = os.path.join(out, stem); os.makedirs(d, exist_ok=True)
                (im if fmt != 'DXT1' else im.convert('RGB')).save(os.path.join(d, base + '.png')); n += 1
            if n: print('%-30s %d textures' % (name, n)); total += n
    print('done: %d textures in %s' % (total, out))

if __name__ == '__main__': main()
