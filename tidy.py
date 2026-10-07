#!/usr/bin/env python3
"""Tidy the modtools folder: moves old helper .bat files, old test folders and obsolete files into modtools\\dev (nothing is deleted).

    python tidy.py          shows what would move and asks before doing it
    python tidy.py --undo   moves everything back

The tools you use every day are not touched: launcher, map2is, compile_map.bat, build_mod, play_solo.bat, gexpad, docs, trenchbroom, ismap, sdk, blender."""
import os, sys, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); DEV = os.path.join(HERE, 'dev')
OLD = ['export_map.bat', 'install_solo.bat', 'try_solo.bat', 'package_map.bat', 'install_models.bat', 'restore_models.bat', 'import_model.bat',
       'test_gun.bat', 'make_console_exe.bat', 'make_shortcut.bat', 'play_map.bat', 'gexpad.bat', 'IronStorm_test.fgd',
       'handgun_test', 'model_samples', 'solo_variants', 'stock_test', 'test_a', 'test_b', 'test_c', 'test_e', 'g',
       'README_TRENCHBROOM.md', 'SCRIPTING.md', 'GEXEDIT.md', 'STOCK_IDS.md', 'STOCK_MODELS.md']
# gexpad.bat and the old documents are replaced by the launcher button and docs\\

def main():
    undo = '--undo' in sys.argv
    src, dst = (DEV, HERE) if undo else (HERE, DEV)
    todo = [n for n in OLD if os.path.exists(os.path.join(src, n)) and not os.path.exists(os.path.join(dst, n))]
    if not todo: print('Nothing to %s.' % ('restore' if undo else 'tidy')); return
    print('Will move %s %s:' % ('into' if not undo else 'out of', 'dev' if not undo else 'dev'))
    for n in todo: print('  ' + n)
    if input('Go ahead? [y/N] ').strip().lower() != 'y': return
    os.makedirs(dst, exist_ok=True)
    for n in todo: shutil.move(os.path.join(src, n), os.path.join(dst, n))
    print('Done.')

if __name__ == '__main__': main()
