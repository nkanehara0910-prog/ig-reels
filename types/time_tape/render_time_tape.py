#!/usr/bin/env python3
"""時間テープ切り型（1日の時間の帯から予定を切り落とし、残った時間を見せる・8秒）。仕様は Notion「仕様書｜時間テープ切り型」。
  python3 types/time_tape/render_time_tape.py posts.json REPO_DIR [--bgm-dir BGM_DIR] [--frames-dir DIR]
（2026-11-26夜、毎晩の投稿作成タスクが仕様書9章のコードから保存。render() と __main__ は tool_demo と同じで3点だけ変更）
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
END = 6.7            # ここからCTA
FIRST = 0.9          # 最初のカット
STEP = 1.05          # カットの間隔
TYPE = '時間テープ切り型'
TX0, TX1 = 130, 500          # テープの横位置
TY0, TY1 = 560, 1500         # テープの縦位置（start時〜end時）
HOOK_CY = 330
SUBT_CY = 1640               # 切った予定の字幕
RX = 560                     # 右側の切った予定リスト・結果の左端
Z.SUB_CY = SUBT_CY           # CTAは下の字幕と同じ位置（テープに重ねない）
PATTERNS = {'A': '問い「〜いつ勉強できるの？」', 'B': '数字の断言「〜自由な時間は○時間だけ」', 'C': '呼びかけ「〜な人、1日を切ってみて」'}
INK = (40, 44, 56, 255)
PAPER = (250, 248, 240, 255)


def check(p):
    e = []
    for k in ('key', 'datetime', 'account', 'pattern', 'title', 'tape', 'caption'):
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
    tp = p['tape']
    for k in ('start', 'end', 'cuts', 'result'):
        if k not in tp:
            e.append(f'tape.{k} がない')
    if e:
        return e
    s, en = int(tp['start']), int(tp['end'])
    if not (0 <= s < en <= 24 and 10 <= en - s <= 18):
        e.append('tape の start〜end は10〜18時間の幅（例 6〜24）')
    cuts = tp['cuts']
    if not 3 <= len(cuts) <= 5:
        e.append('tape.cuts は3〜5個')
    if FIRST + STEP * (len(cuts) - 1) + 0.9 > END:
        e.append('カットが多すぎて結果を見せる時間がない')
    used = set()
    for c in cuts:
        segs = c['hours']
        lab = c['label']
        if Z.zlen(lab) > 9.5:
            e.append(f'cut「{lab}」が長い（9字まで）')
        for a, b in segs:
            if not (s <= a < b <= en):
                e.append(f'cut「{lab}」の時間 {a}〜{b} がテープの外')
            for h in range(int(a), int(b)):
                if h in used:
                    e.append(f'cut「{lab}」の {h}時台が他と重なる')
                used.add(h)
    left = (en - s) - len(used)
    if left <= 0:
        e.append('残りの時間が0')
    r = tp['result'].split('\n')
    if len(r) > 2 or any(Z.zlen(l) > 6.5 for l in r):
        e.append('result は2行・各6字まで')
    if '公式LINE' not in p['caption']:
        e.append('キャプションの締めに「公式LINE」がない')
    if len(p['caption']) > 2200:
        e.append('キャプションが2200字を超えている')
    return e


def F(w, s):
    return Z.F(w, s)


def y_of(h, s, en):
    return TY0 + (TY1 - TY0) * (h - s) / (en - s)


def text_l(L, d, s, f, x, cy, fill):
    bb = f.getbbox('漢')
    draw_line(L, d, s, f, x, cy - (bb[1] + bb[3]) / 2, fill)


def outline_text_c(L, d, s, f, cx, cy, fill, alpha=1.0, stroke=8):
    """手本と同じ白文字＋黒ふち（字幕）"""
    w = line_width(s, f)
    bb = f.getbbox('漢')
    y = cy - (bb[1] + bb[3]) / 2
    d.text((cx - w / 2, y), s, font=f, fill=fill[:3] + (int(255 * alpha),),
           stroke_width=stroke, stroke_fill=(0, 0, 0, int(255 * alpha)))


def scissors(d, x, y, open_=0.5, acc=(255, 90, 90)):
    """横向きのハサミ（刃先が左＝テープ側、持ち手が右）。x,y は支点"""
    a = 10 + 26 * open_
    import math
    for sgn in (-1, 1):
        ang = math.radians(sgn * a / 2)
        ex, ey = x - 230 * math.cos(ang), y + 170 * math.sin(ang)
        d.line([(x, y), (ex, ey)], fill=(205, 210, 220, 255), width=16)
        hx, hy = x + 95 * math.cos(ang), y - 95 * math.sin(ang) + sgn * 30
        d.ellipse([hx - 54, hy - 34, hx + 54, hy + 34], outline=acc + (255,), width=16)
    d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=(120, 124, 134, 255))


def cut_times(n):
    return [FIRST + STEP * k for k in range(n)]


def hook(L, d, title):
    f = F('Black', 74)
    lines = title.split('\n')
    lh = 100
    w = max(line_width(l, f) for l in lines) + 70
    h = len(lines) * lh + 40
    d.rectangle([W / 2 - w / 2, HOOK_CY - h / 2, W / 2 + w / 2, HOOK_CY + h / 2], fill=(0, 0, 0, 205))
    for i, l in enumerate(lines):
        Z.text_c(d, L, l, f, W / 2, HOOK_CY - (len(lines) - 1) * lh / 2 + i * lh, (255, 255, 255, 255))


def frame(p, bg, t):
    acc = Z.ACCENT[p['account']]
    tp = p['tape']
    s, en = int(tp['start']), int(tp['end'])
    cuts = tp['cuts']
    ct = cut_times(len(cuts))
    im = bg.copy()
    L = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    hf = F('Bold', 46)
    owner = {}
    for k, c in enumerate(cuts):
        for a, b in c['hours']:
            for h in range(int(a), int(b)):
                owner[h] = k
    done_all = t >= ct[-1] + 0.6
    sh = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    for h in range(s, en):
        k = owner.get(h)
        if k is not None and t >= ct[k] + 0.15:
            continue
        sd.rectangle([TX0 + 14, y_of(h, s, en) + 14, TX1 + 14, y_of(h + 1, s, en) + 14], fill=(0, 0, 0, 120))
    L.alpha_composite(sh.filter(ImageFilter.GaussianBlur(12)))
    d = ImageDraw.Draw(L)
    for h in range(s, en):
        y0, y1 = y_of(h, s, en), y_of(h + 1, s, en)
        k = owner.get(h)
        dx = dy = 0.0
        a = 1.0
        fill = PAPER
        if k is not None and t >= ct[k] + 0.15:
            q = Z.ease((t - ct[k] - 0.15) / 0.55)
            dx, dy, a = -40 * q, 160 * q * q, 1 - q   # 切れて下に落ちる
            if a <= 0.02:
                continue
            fill = (215, 215, 210, int(255 * a))
        elif k is None and done_all:
            g = Z.ease((t - ct[-1] - 0.6) / 0.4)
            fill = tuple(int(PAPER[i] * (1 - g) + acc[i] * g) for i in range(3)) + (255,)
        d.rectangle([TX0 + dx, y0 + dy, TX1 + dx, y1 + dy], fill=fill)
        d.line([(TX0 + dx, y0 + dy), (TX1 + dx, y0 + dy)], fill=(200, 196, 186, int(255 * a)), width=2)
        d.text((TX0 + 30 + dx, (y0 + y1) / 2 + dy), f'{h}:00', font=hf, fill=INK[:3] + (int(255 * a),), anchor='lm')
    ye = y_of(en, s, en)
    d.text((TX0 + 30, ye + 26), f'{en}:00', font=hf, fill=(220, 224, 232, 200), anchor='lm')
    k_now = None
    for k in range(len(cuts)):
        if ct[k] - 0.55 <= t < ct[k] + 0.25:
            k_now = k
    if k_now is not None:
        top = min(a for a, b in cuts[k_now]['hours'])
        yc = y_of(top, s, en)
        q = Z.ease((t - ct[k_now] + 0.55) / 0.4)
        x = TX1 + 330 - 120 * q
        op = 0.9 if t < ct[k_now] - 0.1 else max(0.0, 0.9 - (t - ct[k_now] + 0.1) / 0.15)
        d.line([(TX0 - 20, yc), (TX1 + 20, yc)], fill=(255, 80, 90, 170), width=4)
        scissors(d, x, yc, op)
    lf = F('Bold', 52)
    for k, c in enumerate(cuts):
        if t < ct[k]:
            continue
        q = Z.ease((t - ct[k]) / 0.35)
        yy = TY0 + 400 + k * 96
        a = int(255 * q)
        txt = c['label']
        text_l(L, d, '× ' + txt, lf, RX, yy, (190, 196, 210, a))
        w = line_width('× ' + txt, lf)
        d.line([(RX + 50, yy + 2), (RX + 50 + (w - 50) * q, yy + 2)], fill=(255, 110, 120, a), width=4)
    if done_all:
        g = Z.ease((t - ct[-1] - 0.6) / 0.4)
        rf = F('Black', 124)
        for i, l in enumerate(tp['result'].split('\n')):
            text_l(L, d, l, rf, RX, TY0 + 90 + i * 150, acc + (int(255 * g),))
    if t < END:
        sub = None
        for k, c in enumerate(cuts):
            if ct[k] - 0.55 <= t:
                sub = c.get('sub', c['label'])
        if done_all:
            sub = tp.get('sub_result', sub)
        if sub:
            outline_text_c(L, d, sub, F('Black', 64), W / 2, SUBT_CY, (255, 255, 255, 255))
    hook(L, d, p['title'])
    if t >= END:
        Z.draw_sub(L, d, Z.CTA, Z.ease((t - END) / 0.4))
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
        for tt in (0.3, 0.9, 1.3, 3.0, 5.5, 6.5, 7.7):
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
