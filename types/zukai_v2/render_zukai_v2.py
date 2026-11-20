#!/usr/bin/env python3
"""図解アニメ改善版「数字見出し＋3ステップ（8秒）」。仕様は Notion の仕様書。
  python3 types/zukai_v2/render_zukai_v2.py posts.json REPO_DIR [--bgm-dir BGM_DIR] [--frames-dir DIR]
（分析タスク版はこの環境に届かないため、2026-11-20夜に仕様書9章のコードから保存したもの）
"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'zukai_anime'))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
import render_zukai as Z
import bgm_util
from PIL import Image, ImageDraw

W, H, FPS = Z.W, Z.H, Z.FPS
TOTAL = 8.0
END = 6.6
OPEN = 1.5
TYPE = '図解アニメ改善版'


def check(p):
    e = []
    for k in ('key', 'datetime', 'account', 'pattern', 'title', 'steps', 'caption'):
        if k not in p:
            e.append(f'{k} がない')
    if e:
        return e
    if p['account'] not in Z.ACCENT:
        e.append('account は 保護者／受験生')
    if p['pattern'] not in ('A', 'B', 'C'):
        e.append('pattern は A／B／C')
    if p['pattern'] == 'B' and not p.get('big'):
        e.append('パターンBは big（大きい数字）が必要')
    lines = p['title'].split('\n')
    if len(lines) > 2 or any(Z.zlen(l) > 12.5 for l in lines):
        e.append('title は2行・各12字まで')
    if not any(c.isdigit() or c in '一二三四五六七八九十' for c in p['title']):
        e.append('title に数字を入れる（数字見出し）')
    if len(p['steps']) != 3:
        e.append('steps は3つ')
    for s in p['steps']:
        if Z.zlen(s) > 14.5:
            e.append(f'step「{s}」が長い（14字まで）')
    if '公式LINE' not in p['caption']:
        e.append('キャプションの締めに「公式LINE」がない')
    if len(p['caption']) > 2200:
        e.append('キャプションが2200字を超えている')
    return e


def title_at(L, d, title, cy, size, alpha=1.0):
    f = Z.F('Black', size)
    lines = title.split('\n')
    lh = int(size * 1.28)
    for i, l in enumerate(lines):
        Z.text_c(d, L, l, f, W / 2, cy - (len(lines) - 1) * lh / 2 + i * lh, (255, 255, 255, int(255 * alpha)))


def frame(p, bg, t):
    acc = Z.ACCENT[p['account']]
    im = bg.copy()
    L = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    G = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d, gd = ImageDraw.Draw(L), ImageDraw.Draw(G)
    pat = p['pattern']
    data = {'items': p['steps']}
    if t >= END:
        Z.draw_steps(G, gd, data, 9999, acc)
        title_at(L, d, p['title'], Z.HOOK_CY, 80)
        Z.draw_sub(L, d, Z.CTA, Z.ease((t - END) / 0.4))
    elif pat == 'A':
        if t < OPEN:
            title_at(L, d, p['title'], 860, 104)
        else:
            q = Z.ease((t - OPEN) / 0.35)
            title_at(L, d, p['title'], 860 + (Z.HOOK_CY - 860) * q, 104 + (80 - 104) * q)
            Z.draw_steps(G, gd, data, t - OPEN - 0.3, acc)
    elif pat == 'B':
        title_at(L, d, p['title'], Z.HOOK_CY, 80)
        if t < OPEN:
            a = 1.0 if t < OPEN - 0.25 else (OPEN - t) / 0.25
            sc = 0.85 + 0.15 * Z.ease(t / 0.35)
            bf = Z.F('Black', int(300 * sc))
            gd.text((W / 2, 980), p['big'], font=bf, fill=Z.rgba(acc, a), anchor='mm')
        else:
            Z.draw_steps(G, gd, data, t - OPEN, acc)
    else:
        title_at(L, d, p['title'], Z.HOOK_CY, 80)
        Z.draw_steps(G, gd, data, 0.45 + t * (0.7 / 0.6), acc)
    Z.glow_compose(im, G)
    im.alpha_composite(L)
    ImageDraw.Draw(im).rectangle([0, 0, W * t / TOTAL, 7], fill=Z.rgba(acc, 1))
    Z.draw_brand(im)
    return im.convert('RGB')


def render(p, repo, bgm_dir, idx=0, frames_dir=None):
    bg = Z.background(Z.ACCENT[p['account']])
    out = os.path.join(repo, 'videos', p['key'] + '.mp4')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bgm = Z.pick_bgm(p, bgm_dir, idx) if bgm_dir else None
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
           '-r', str(FPS), '-i', '-']
    if bgm:
        bsrc, bst = bgm_util.resolve(bgm_dir, bgm, TOTAL)
        cmd += ['-ss', f'{bst:.2f}', '-i', bsrc, '-filter_complex',
                f'[1:a]atrim=0:{TOTAL:.3f},asetpts=N/SR/TB,volume=0.8,afade=t=in:d=0.3,afade=t=out:st={TOTAL-0.8:.2f}:d=0.8[a]',
                '-map', '0:v', '-map', '[a]']
    else:
        cmd += ['-f', 'lavfi', '-t', f'{TOTAL:.3f}', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
                '-map', '0:v', '-map', '1:a']
    cmd += ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
            '-b:a', '160k', '-ar', '44100', '-t', f'{TOTAL:.3f}', '-movflags', '+faststart', out]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(int(TOTAL * FPS)):
        pr.stdin.write(frame(p, bg, i / FPS).tobytes())
    pr.stdin.close()
    if pr.wait():
        raise SystemExit('ffmpeg 失敗: ' + p['key'])
    if frames_dir:
        os.makedirs(frames_dir, exist_ok=True)
        for tt in (0.3, 1.0, 2.0, 3.5, 5.5, 7.7):
            frame(p, bg, tt).save(os.path.join(frames_dir, f'{p["key"]}_{tt:04.1f}.png'))
    return out, bgm


if __name__ == '__main__':
    args = sys.argv[1:]
    opts = {}
    for k in ('--bgm-dir', '--frames-dir'):
        if k in args:
            i = args.index(k); opts[k] = args[i + 1]; del args[i:i + 2]
    posts_path, repo = args
    posts = json.load(open(posts_path, encoding='utf-8'))
    errs = [f'{p.get("key")}: {e}' for p in posts for e in check(p)]
    if errs:
        raise SystemExit('チェックに失敗:\n' + '\n'.join(errs))
    by_day, s_idx = {}, 0
    for p in posts:
        out, bgm = render(p, repo, opts.get('--bgm-dir'), s_idx, opts.get('--frames-dir'))
        s_idx += p['account'] == '受験生'
        print(f'OK {out} {TOTAL}秒 bgm={bgm}')
        if p['key'].startswith('proto_'):
            continue
        item = {k: p[k] for k in ('key', 'datetime', 'account', 'title', 'caption')}
        item.update(type=TYPE, video=f'videos/{p["key"]}.mp4', bgm=(bgm or '').replace('.m4a', ''))
        for k in ('pattern', 'grade'):
            if p.get(k):
                item[k] = p[k]
        by_day.setdefault(p['datetime'][:10].replace('/', '-'), []).append(item)
    for day, items in by_day.items():
        qp = os.path.join(repo, 'queue', f'{day}.json')
        cur = json.load(open(qp, encoding='utf-8')) if os.path.exists(qp) else []
        keys = {i['key'] for i in items}
        cur = [c for c in cur if c['key'] not in keys] + items
        with open(qp, 'w', encoding='utf-8') as f:
            json.dump(cur, f, ensure_ascii=False, indent=1)
        print(f'queue/{day}.json: {len(cur)}件')
