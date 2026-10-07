"""Event-box scene (<level>_event_boxes.4X3): named trigger volumes the scripts react to.

A box is a LIST SECT named "Event_<name>"; the engine calls the script functions <name>_server_enter / _server_stay /
_server_exit for characters inside. Each box is a convex BSP of six planes (n.x + d > 0 is inside) in game units.
Axis-aligned boxes always use the same tree, so a stock box (from lv1_event_boxes.4X3) is used as a template and only
the six plane distances, the name and the bounding sphere change (verified against 22 stock boxes):
  planes (+y, -x, -y, +x, +z, -z): d = -ymin, xmax, ymax, -xmin, -zmin, zmax;  sphere = centre, 1.0, half diagonal."""
import base64, math, struct

_HDR = base64.b64decode(
    "UklGRuqnAQBTQ0VONFgudigAAAAIAAEABQDCBCRmbngudmVyADEuOC4xMjE4LjUAAAAAAAAAAAAAAAAAQG5hbSkA"
    "AAA0WCBTdHVkaW8gQnVpbGRlciBHZW5lcmF0ZWQgRXZlbnRzIFNjZW5lAABBdXBtBAAAAAAAgD8=")
_SECT = base64.b64decode(
    "TElTVKQCAABTRUNUQG5hbRAAAABFdmVudF9zY2VuZV8xXzEAc3BochQAAAAMPDrFaQ1sQreAs8MAAIA/JE3yQUxJ"
    "U1RkAgAAQlNQIHJvb3RYAgAAAAAAAAAAgD8AAAAA4/E8wgAAAAADAAAAAACAvwAAAAAAAAAAxB85xQAAAAADAAAA"
    "AAAAAAAAgL8AAAAAeJSNQgAAAAADAAAAAACAPwAAAAAAAACAVFg7RQAAAAADAAAAAAAAAAAAAAAAAIA/00K+QwAA"
    "AAADAAAAAAAAAAAAAAAAAIC/m76owwAAAAADAAAACMDDE3gBhQAAAAAA/////wEAAAAAAAAAAAAAAAAAAAAAAIC/"
    "m76owwAAAAADAAAACMDDE3gBhQAAAAAA/////wEAAAAAAAAACMDDE3gBhQAAAAAA/////wIAAAAAAAAAAAAAAAAA"
    "AIAAAIA/00K+QwAAAAADAAAACMDDE3gBhQAAAAAA/////wEAAAAAAAAACMDDE3gBhQAAAAAA/////wIAAAAAAAAA"
    "AACAPwAAAAAAAAAAVFg7RQAAAAADAAAACMDDE3gBhQAAAAAA/////wEAAAAAAAAACMDDE3gBhQAAAAAA/////wIA"
    "AAAAAAAAAAAAAAAAgL8AAAAAeJSNQgAAAAADAAAACMDDE3gBhQAAAAAA/////wEAAAAAAAAACMDDE3gBhQAAAAAA"
    "/////wIAAAAAAAAAAACAvwAAAAAAAAAAxB85xQAAAAADAAAACMDDE3gBhQAAAAAA/////wEAAAAAAAAACMDDE3gB"
    "hQAAAAAA/////wIAAAAAAAAAAAAAAAAAgD8AAACA4/E8wgAAAAADAAAACMDDE3gBhQAAAAAA/////wEAAAAAAAAA"
    "CMDDE3gBhQAAAAAA/////wIAAAAAAAAA")
_PAYLOAD = _SECT.find(b'BSP root') + 12            # the 600-byte plane tree

def _section(name, lo, hi):
    nm = ('Event_' + name).encode() + b'\0'
    if len(nm) % 2: nm += b'\0'
    d_old = [_SECT[_PAYLOAD + 24*k + 12:_PAYLOAD + 24*k + 16] for k in range(6)]
    d_new = [-lo[1], hi[0], hi[1], -lo[0], -lo[2], hi[2]]
    tree = bytearray(_SECT[_PAYLOAD:_PAYLOAD + 600])
    for old, v in zip(d_old, d_new):
        nb = struct.pack('<f', v); i = 0
        while True:
            i = bytes(tree).find(old, i)
            if i < 0: break
            tree[i:i+4] = nb; i += 4
    c = [(lo[k] + hi[k]) / 2 for k in range(3)]
    r = 0.5 * math.sqrt(sum((hi[k] - lo[k]) ** 2 for k in range(3)))
    bsp = b'BSP ' + b'root' + struct.pack('<I', 600) + bytes(tree)
    body = (b'SECT' + b'@nam' + struct.pack('<I', len(nm) if len(nm) % 2 == 0 and nm[-2:] != b'\0\0' else len(nm) - 1) + nm
            + b'sphr' + struct.pack('<I', 20) + struct.pack('<5f', c[0], c[1], c[2], 1.0, r)
            + b'LIST' + struct.pack('<I', len(bsp)) + bsp)
    return b'LIST' + struct.pack('<I', len(body)) + body

def build(boxes):
    """boxes: [(name, (xmin, ymin, zmin), (xmax, ymax, zmax))] in game units -> file bytes"""
    out = bytearray(_HDR)
    for name, lo, hi in boxes: out += _section(name, lo, hi)
    struct.pack_into('<I', out, 4, len(out) - 8)
    return bytes(out)
