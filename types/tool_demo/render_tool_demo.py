#!/usr/bin/env python3
"""ツール画面デモ型（PC画面で学習ツールが動く＋上の一言フック・8秒）。仕様は Notion「仕様書｜ツール画面デモ型」。
  python3 types/tool_demo/render_tool_demo.py posts.json REPO_DIR [--bgm-dir BGM_DIR] [--frames-dir DIR]
"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'zukai_anime'))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
import render_zukai as Z
import bgm_util
from render_qa import draw_line, line_width
from PIL import Image, ImageDraw, ImageFilter

W, H, FPS = Z.W, Z.H, Z.FPS
TOTAL = 8.0
END = 6.6
CLICK = 1.3
TYPE = 'ツール画面デモ型'
SCR = (70, 560, 1010, 1440)
HOOK_CY = 330
PATTERNS = {'A': '一瞬でわかる', 'B': '〜な人、これ使って', 'C': '僕が受験生のとき欲しかった'}


def check(p):
    e = []
    for k in ('key', 'datetime', 'account', 'pattern', 'title', 'tool', 'caption'):
        if k not in p:
            e.append(f'{k} がない')
    if e:
        return e
    if p['account'] not in Z.ACCENT:
        e.append('account は 保護者／受験生')
    if p['pattern'] not in PATTERNS:
        e.append('pattern は A／B／C')
    tl = p['title'].split('\n')
    if len(tl) > 2 or any(Z.zlen(l) > 11.5 for l in tl):
        e.append('title は2行・各11字まで')
    t = p['tool']
    for k in ('name', 'inputs', 'button', 'rows'):
        if k not in t:
            e.append(f'tool.{k} がない')
    if e:
        return e
    if Z.zlen(t['name']) > 14.5:
        e.append('tool.name は14字まで')
    if not 1 <= len(t['inputs']) <= 2:
        e.append('tool.inputs は1〜2行')
    for a, b in t['inputs']:
        if Z.zlen(a) > 4.5 or Z.zlen(b) > 12.5:
            e.append(f'input「{a}｜{b}」が長い（4字／12字まで）')
    if Z.zlen(t['button']) > 7.5:
        e.append('tool.button は7字まで')
    if not 3 <= len(t['rows']) <= 4:
        e.append('tool.rows は3〜4行')
    for r in t['rows']:
        if Z.zlen(r[0]) > 6.5 or Z.zlen(r[1]) > 10.5:
            e.append(f'row「{r[0]}｜{r[1]}」が長い（6字／10字まで）')
        if len(r) > 2 and not 0 <= float(r[2]) <= 1:
            e.append('row の3つ目（バーの長さ）は0〜1')
    if '公式LINE' not in p['caption']:
        e.append('キャプションの締めに「公式LINE」がない')
    if len(p['caption']) > 2200:
        e.append('キャプションが2200字を超えている')
    return e


def F(w, s):
    return Z.F(w, s)


def text_l(L, d, s, f, x, cy, fill):
    bb = f.getbbox('漢')
    draw_line(L, d, s, f, x, cy - (bb[1] + bb[3]) / 2, fill)


def text_r(L, d, s, f, xr, cy, fill):
    text_l(L, d, s, f, xr - line_width(s, f), cy, fill)


def device(base):
    x0, y0, x1, y1 = SCR
    sh = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([x0 - 10, y0 + 10, x1 + 30, y1 + 60], 40, fill=(0, 0, 0, 170))
    base.alpha_composite(sh.filter(ImageFilter.GaussianBlur(30)))
    d = ImageDraw.Draw(base)
    d.rounded_rectangle([x0 - 26, y0 - 26, x1 + 26, y1 + 26], 34, fill=(28, 30, 36, 255), outline=(70, 74, 84, 255), width=3)
    d.rounded_rectangle([x0, y0, x1, y1], 14, fill=(246, 247, 250, 255))
    d.rounded_rectangle([x0, y0, x1, y0 + 70], 14, fill=(226, 229, 236, 255))
    d.rectangle([x0, y0 + 50, x1, y0 + 70], fill=(226, 229, 236, 255))
    for i, c in enumerate([(255, 95, 87), (255, 189, 46), (40, 200, 64)]):
        d.ellipse([x0 + 24 + i * 34, y0 + 24, x0 + 46 + i * 34, y0 + 46], fill=c)
    d.rounded_rectangle([x0 + 150, y0 + 16, x1 - 30, y0 + 54], 19, fill=(255, 255, 255, 255))
    d.text((x0 + 175, y0 + 35), 'medwolf-tools / 無料ツール', font=F('Medium', 24), fill=(110, 116, 130), anchor='lm')
    d.polygon([(x0 - 70, y1 + 40), (x1 + 70, y1 + 40), (x1 + 140, y1 + 150), (x0 - 140, y1 + 150)], fill=(48, 51, 58, 255))
    for r in range(3):
        yy = y1 + 58 + r * 30
        for k in range(14):
            xx = x0 - 50 + k * 72 - r * 22
            d.rounded_rectangle([xx, yy, xx + 60, yy + 22], 5, fill=(30, 32, 37, 255))
    return base


def cursor(L, x, y, press=0.0):
    d = ImageDraw.Draw(L)
    s = 1.0 - 0.15 * press
    pts = [(0, 0), (0, 52), (13, 40), (23, 63), (32, 59), (22, 37), (40, 37)]
    pts = [(x + px * s, y + py * s) for px, py in pts]
    d.polygon(pts, fill=(20, 20, 24, 255), outline=(255, 255, 255, 255))
    d.line(pts + [pts[0]], fill=(255, 255, 255, 255), width=3)


def tool_ui(L, d, p, t, acc):
    x0, y0, x1, y1 = SCR
    tl = p['tool']
    ink, sub = (24, 28, 40, 255), (110, 116, 130, 255)
    accd = tuple(int(c * 0.78) for c in acc)
    cx = x0 + 50
    text_l(L, d, tl['name'], F('Black', 50), cx, y0 + 135, ink)
    d.line([(cx, y0 + 168), (x1 - 50, y0 + 168)], fill=(220, 223, 230, 255), width=2)
    y = y0 + 220
    for a, b in tl['inputs']:
        text_l(L, d, a, F('Bold', 34), cx, y, sub)
        d.rounded_rectangle([cx + 150, y - 30, x1 - 50, y + 30], 12, fill=(255, 255, 255, 255), outline=(205, 209, 218, 255), width=2)
        text_l(L, d, b, F('Bold', 36), cx + 172, y, ink)
        y += 82
    bx0, by0, bx1, by1 = cx, y - 18, x1 - 50, y + 54
    press = max(0.0, 1 - abs(t - CLICK) / 0.15) if t < CLICK + 0.15 else 0.0
    shade = 1.0 - 0.18 * press
    d.rounded_rectangle([bx0, by0, bx1, by1], 16, fill=tuple(int(c * shade) for c in accd) + (255,))
    Z.text_c(d, L, tl['button'], F('Black', 34), (bx0 + bx1) / 2, (by0 + by1) / 2, (255, 255, 255, 255))
    if CLICK <= t < CLICK + 0.5:
        q = (t - CLICK) / 0.5
        r = 30 + 160 * q
        cxp, cyp = (bx0 + bx1) / 2 + 120, (by0 + by1) / 2
        d.ellipse([cxp - r, cyp - r, cxp + r, cyp + r], outline=Z.rgba(acc, 1 - q), width=6)
    ry = by1 + 60
    rows = tl['rows']
    rh = (y1 - 40 - ry) / len(rows)
    for k, r in enumerate(rows):
        q = Z.ease((t - CLICK - 0.35 - 0.45 * k) / 0.4)
        if q <= 0:
            continue
        yy = ry + k * rh + rh / 2 + 18 * (1 - q)
        a = int(255 * q)
        text_l(L, d, r[0], F('Bold', 40), cx, yy, (ink[0], ink[1], ink[2], a))
        frac = float(r[2]) if len(r) > 2 else 0.35 + 0.15 * k
        bw0, bw1 = cx + 250, x1 - 280
        d.rounded_rectangle([bw0, yy - 16, bw1, yy + 16], 16, fill=(232, 235, 241, a))
        fw = (bw1 - bw0) * frac * Z.ease((t - CLICK - 0.45 - 0.45 * k) / 0.6)
        if fw > 32:
            d.rounded_rectangle([bw0, yy - 16, bw0 + fw, yy + 16], 16, fill=Z.rgba(acc, q))
        text_r(L, d, r[1], F('Black', 42), x1 - 50, yy, (accd[0], accd[1], accd[2], a))


def hook(L, d, title, alpha=1.0):
    f = F('Black', 74)
    lines = title.split('\n')
    lh = 100
    w = max(line_width(l, f) for l in lines) + 70
    h = len(lines) * lh + 40
    d.rectangle([W / 2 - w / 2, HOOK_CY - h / 2, W / 2 + w / 2, HOOK_CY + h / 2], fill=(0, 0, 0, int(205 * alpha)))
    for i, l in enumerate(lines):
        Z.text_c(d, L, l, f, W / 2, HOOK_CY - (len(lines) - 1) * lh / 2 + i * lh, (255, 255, 255, int(255 * alpha)))


def cursor_pos(p, t):
    x0, y0, x1, y1 = SCR
    n_in = len(p['tool']['inputs'])
    by = y0 + 220 + 82 * n_in + 18
    tx, ty = (x0 + x1) / 2 + 120, by
    sx, sy = x1 - 60, y1 + 120
    if t < 0.3:
        return sx, sy
    if t < CLICK:
        q = Z.ease((t - 0.3) / (CLICK - 0.3))
        return sx + (tx - sx) * q, sy + (ty - sy) * q
    q = Z.ease((t - CLICK - 0.6) / 1.0)
    return tx + (x0 + 40 - tx) * q, ty + (y1 + 70 - ty) * q


def frame(p, bg, t):
    acc = Z.ACCENT[p['account']]
    im = bg.copy()
    L = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    tool_ui(L, d, p, t, acc)
    hook(L, d, p['title'])
    cx, cy = cursor_pos(p, t)
    press = max(0.0, 1 - abs(t - CLICK) / 0.15)
    cursor(L, cx, cy, press)
    if t >= END:
        Z.draw_sub(L, d, Z.CTA, Z.ease((t - END) / 0.4))
    im.alpha_composite(L)
    ImageDraw.Draw(im).rectangle([0, 0, W * t / TOTAL, 7], fill=Z.rgba(acc, 1))
    Z.draw_brand(im)
    return im.convert('RGB')


def render(p, repo, bgm_dir, idx=0, frames_dir=None):
    bg = device(Z.background(Z.ACCENT[p['account']]))
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
        for tt in (0.3, 1.0, 1.4, 2.5, 4.0, 7.7):
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
