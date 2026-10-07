"""Change the first-person arms the player sees (the whole game, every level, in this working copy only).

usage:
  python set_arms.py trooper        use trooper arms
  python set_arms.py restore        back to the normal hero arms

Arms that exist in the game: kasakh, lobby, russian, sibbourrin1, sibsniper, supercadet, trooper (and wiz = normal).
The game always loads wiz_model_first.4x3 for the player's arms, so this copies the chosen arms over that entry
in Models.ibf. Models.ibf.bak (made automatically the first time anything is installed) keeps the stock archive.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ismap import bigfile

ARMS = {'kasakh': 'kasakh_model_first.4x3', 'lobby': 'Lobby_model_first.4x3', 'russian': 'russian_model_first.4x3',
        'sibbourrin1': 'sibbourrin1_model_first.4x3', 'sibsniper': 'sibsniper_model_first.4x3',
        'supercadet': 'supercadet_model_first.4x3', 'trooper': 'trooper_model_first.4x3', 'wiz': 'wiz_model_first.4x3'}

def main():
    if len(sys.argv) != 2 or (sys.argv[1] not in ARMS and sys.argv[1] != 'restore'):
        print(__doc__); return 1
    game = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ibf, lst = os.path.join(game, 'Models.ibf'), os.path.join(game, 'Models.lst')
    choice = 'wiz' if sys.argv[1] == 'restore' else sys.argv[1]
    if os.path.exists(ibf + '.bak'): src_ibf, src_lst = ibf + '.bak', lst + '.bak'     # stock copies
    else: src_ibf, src_lst = ibf, lst
    data = bigfile.read_file(src_ibf, src_lst, ARMS[choice])
    if data is None: sys.exit('could not find %s in the stock Models.ibf' % ARMS[choice])
    bigfile.replace_files(ibf, lst, {'wiz_model_first.4x3': data})
    print('player arms are now: %s' % choice)

if __name__ == '__main__':
    sys.exit(main())
