import struct,sys,zlib
def chunks(b,off,end):
    while off+8<=end:
        cid=b[off:off+4];sz=struct.unpack_from('<I',b,off+4)[0]
        if sz>end-off-8: yield cid,off+8,sz,True;return
        yield cid,off+8,sz,False
        off+=8+sz+(sz&1)
def unz(p):
    tag=p[:4];n=struct.unpack_from('<I',p,4)[0]
    d=zlib.decompressobj(-15)
    out=d.decompress(p[8:])
    return tag,n,out
def dump(b,off,end,d=0,maxd=6,lim=12):
    n=0
    for cid,o,sz,bad in chunks(b,off,end):
        n+=1
        if n>lim: print('  '*d+'...');break
        nm=cid.decode('latin1');ex=''
        if bad: print('  '*d+f'{nm} BADSIZE {sz}');break
        if cid==b'zip!':
            try:
                tag,n_,out=unz(b[o:o+sz]);ex=f' tag={tag} claimed={n_} got={len(out)} head={out[:16].hex(" ")}'
            except Exception as e: ex=' ERR '+str(e)
        elif cid in(b'LIST',b'ALIS'): ex=' form='+b[o:o+4].decode('latin1')
        print('  '*d+f'{nm} sz={sz}{ex}', b[o:o+min(sz,24)].hex(' ') if cid not in(b'LIST',b'ALIS',b'zip!') else '')
        if cid in(b'LIST',b'ALIS') and d<maxd: dump(b,o+4,o+sz,d+1,maxd,lim)
if __name__=='__main__':
    b=open(sys.argv[1],'rb').read()
    dump(b,12,len(b),0,int(sys.argv[2]) if len(sys.argv)>2 else 6,int(sys.argv[3]) if len(sys.argv)>3 else 12)
