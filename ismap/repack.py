import struct,zlib,sys

from .p4x3 import chunks
def read_map(path):
    return read_map_bytes(open(path,'rb').read())
def read_map_bytes(b):
    head=[];recs=[];tags=[];claimed=[]
    d=zlib.decompressobj(-15)
    for cid,o,sz,bad in chunks(b,12,len(b)):
        if cid==b'zip!':
            tags.append(b[o:o+4]);claimed.append(struct.unpack_from('<I',b,o+4)[0])
            recs.append(d.decompress(b[o+8:o+sz]))
        else: head.append((cid,b[o:o+sz]))
    return head,recs,tags,claimed
def chunk(cid,data):
    return cid+struct.pack('<I',len(data))+data+(b'\0' if len(data)&1 else b'')
def write_map(path,head,recs,tags=None,flush=zlib.Z_SYNC_FLUSH):
    body=b''.join(chunk(c,d) for c,d in head)
    co=zlib.compressobj(9,zlib.DEFLATED,-15)
    for i,r in enumerate(recs):
        z=co.compress(r)+co.flush(flush)
        tag=(tags[i] if tags else b'TEXU')
        body+=chunk(b'zip!',tag+struct.pack('<I',len(r)+4)+z)
    out=b'RIFF'+struct.pack('<I',len(body)+4)+b'SCEN'+body
    open(path,'wb').write(out)
    return out
if __name__=='__main__':
    src,dst=sys.argv[1:3]
    head,recs,tags,claimed=read_map(src)
    out=write_map(dst,head,recs,tags)
    h2,r2,t2,c2=read_map(dst)
    print('records equal:',r2==recs,'| head equal:',h2==head,'| tags',set(tags),'| claimed=len+4:',all(c==len(r)+4 for c,r in zip(claimed,recs)))
    print('size src',len(open(src,'rb').read()),'dst',len(out))
