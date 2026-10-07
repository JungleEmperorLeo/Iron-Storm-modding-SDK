"""Put imported models into the game's Models.ibf (the stock archive is kept as Models.ibf.bak) or take them out again.

  python models_install.py install imported_models      (copy every file of the folder into the game)
  python models_install.py restore                      (back to the stock Models.ibf)"""
import os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from ismap import bigfile
game = os.path.dirname(HERE); ibf = os.path.join(game, 'Models.ibf'); lst = os.path.join(game, 'Models.lst')
if len(sys.argv) >= 3 and sys.argv[1] == 'install':
    d = sys.argv[2] if os.path.isabs(sys.argv[2]) else os.path.join(HERE, sys.argv[2])
    files = {n: open(os.path.join(d, n), 'rb').read() for n in os.listdir(d) if n.lower().endswith(('.4x3', '.4xt'))}
    bigfile.replace_files(ibf, lst, files); print('installed:', ', '.join(files))
elif len(sys.argv) >= 2 and sys.argv[1] == 'restore':
    for p in (ibf, lst):
        if os.path.exists(p + '.bak'): shutil.copy2(p + '.bak', p)
    print('restored the stock Models.ibf')
else: print(__doc__)
