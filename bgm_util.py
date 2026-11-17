"""
BGMの選び方（全部の型で共通。2026-11-17 くろさん指定）
- 曲はループさせない（つなぎ目で曲が頭に戻って不自然になるため）
- 8秒の切り出し（ig-reels-private/bgm/<曲>.m4a）で足りるときはそれを使う
- 動画が8秒より長いときは、長い音源 ig-reels-private/bgm/long/<曲>.(m4a|mp3|wav) を使う。
  starts.json の切り出し開始位置（サビ）から必要な長さだけ切る。曲の終わりに届くときは開始位置を前にずらす
- 長い音源もないときは止める（ループで埋めない）
"""
import json, os, subprocess

EXTS = ('.m4a', '.mp3', '.wav', '.aac', '.flac')


def duration(path):
    return float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                          '-of', 'csv=p=0', path]).decode().strip() or 0)


def resolve(bgm_dir, name, need):
    """(音源のパス, 開始秒) を返す。name は 'In-Between' または 'In-Between.m4a'"""
    base = name[:-4] if name.endswith('.m4a') else name
    clip = os.path.join(bgm_dir, base + '.m4a')
    if os.path.exists(clip) and duration(clip) + 0.01 >= need:
        return clip, 0.0
    long_dir = os.path.join(bgm_dir, 'long')
    for ext in EXTS:
        lp = os.path.join(long_dir, base + ext)
        if os.path.exists(lp):
            ld = duration(lp)
            if ld + 0.01 < need:
                break
            st = 0.0
            sp = os.path.join(bgm_dir, 'starts.json')
            if os.path.exists(sp):
                st = float((json.load(open(sp)).get(base) or [0])[0])
            st = max(0.0, min(st, ld - need - 0.05))
            return lp, st
    raise SystemExit(f'BGM {base}: 動画 {need:.1f}秒に足りる音源がない（8秒の切り出ししかない）。'
                     f'曲はループしないので、{long_dir}/{base}.m4a に長い音源（元の曲）を置くか、動画を8秒以内にする')
