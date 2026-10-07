"""Build the <map>_light.4x3 file: a RIFF 'SCEN' with the 3 header chunks of a template
followed by one LIST/LOMN per point light (name, xfr, $col, Amul, Aane, Aafs, Aafe, lflg)."""
import struct
from .p4x3 import chunks

def _chunk(cid, data):
    return cid + struct.pack('<I', len(data)) + data + (b'\0' if len(data) & 1 else b'')

def _light(name, pos, rgb, mul, start, end):
    xfr = struct.pack('<16f', 1,0,0,0, 0,1,0,0, 0,0,1,0, pos[0],pos[1],pos[2],1) + bytes.fromhex('05030000')
    body = (_chunk(b'@nam', name.encode() + b'\0') + _chunk(b'\x11xfr', xfr) +
            _chunk(b'$col', struct.pack('<4f', rgb[0], rgb[1], rgb[2], 0.0)) +
            _chunk(b'Amul', struct.pack('<f', mul)) + _chunk(b'Aane', struct.pack('<f', 0.0)) +
            _chunk(b'Aafs', struct.pack('<f', start)) + _chunk(b'Aafe', struct.pack('<f', end)) +
            _chunk(b'lflg', struct.pack('<I', 2)))
    return _chunk(b'LIST', b'LOMN' + body)

def build(template, lights, sun=None):
    """lights: list of dict(pos, rgb(0..1), mul, start, end). sun: optional (pos, rgb) for the DYNA_sun entry."""
    head = b''; sun_chunk = None
    for cid, o, sz, bad in chunks(template, 12, len(template)):
        raw = template[o-8:o+sz+(sz & 1)]
        if cid != b'LIST': head += raw
        elif b'DYNA_sun' in raw[:40] and sun_chunk is None: sun_chunk = bytearray(raw)
    body = head
    if sun is not None and sun_chunk is not None:
        i = sun_chunk.find(b'\x11xfr') + 8
        struct.pack_into('<3f', sun_chunk, i + 48, *sun[0])
        body += bytes(sun_chunk)
    elif sun_chunk is not None:
        body += bytes(sun_chunk)
    for k, l in enumerate(lights):
        body += _light('DYNA_map_%03d' % k, l['pos'], l['rgb'], l['mul'], l['start'], l['end'])
    return b'RIFF' + struct.pack('<I', len(body) + 4) + b'SCEN' + body
