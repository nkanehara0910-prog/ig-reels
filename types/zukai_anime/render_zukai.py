#!/usr/bin/env python3
"""
図解アニメ（モーショングラフィック解説）リールの生成。仕様は Notion「仕様書｜図解アニメ」。
  python3 types/zukai_anime/render_zukai.py posts.json REPO_DIR --bgm-dir BGM_DIR [--frames t1,t2,...]
posts の各要素: key, datetime("YYYY/MM/DD HH:MM"), account(保護者/受験生), title, caption,
  scenes: [{kind: countdown|bars|steps|boxes, sub: "字幕(\\n で2行まで)", head?: "見出し", dur?: 秒, data: {...}}]
  data:
    countdown: {from, to, unit?, left?, right?}
    bars:      {items: [{label, value, unit?, hl?}]}（4本まで）
    steps:     {items: ["…", …]}（3〜4個・14字まで）
    boxes:     {n, fill, counter_unit?, labels?: [...]}
出力: REPO_DIR/videos/<key>.mp4、REPO_DIR/queue/<投稿日>.json に追記（同じ key 以外は消さない）
--frames を付けると、各動画の確認用コマ（PNG）を REPO_DIR の外の --frames-dir に書き出す。
"""
import json, math, os, subprocess, sys
from datetime import date
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
from render_qa import draw_line, line_width  # 絵文字つきの行の描画を共用

W, H, FPS = 1080, 1920, 30
FD = '/usr/share/fonts/opentype/noto/'
def F(w, s):
    # 明朝体（Noto Serif CJK JP = 源ノ明朝）。index=0 が JP
    return ImageFont.truetype(FD + f'NotoSerifCJK-{w}.ttc', s, index=0)

ACCENT = {'受験生': (79, 209, 255), '保護者': (255, 184, 107)}
RED = (255, 110, 120)
PARENT_BGM = 'In-Between.m4a'
LOOP = 1.6
BRAND = '現役医大生塾 MedWolf'
LOGO = os.path.abspath(os.path.join(HERE, '..', '..', 'assets', 'brand', 'medwolf_badge.png'))
_LOGO = {}
CTA = '詳細はキャプションをチェック✅'
SUB_CY, HOOK_CY, HEAD_CY = 1480, 330, 320
KINDS = ('countdown', 'bars', 'steps', 'boxes')


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def zlen(s):
    """全角換算の文字数（半角英数は0.5）"""
    return sum(0.5 if ord(c) < 0x2000 else 1 for c in s)


# ---------- チェック ----------
def check(p):
    errs = []
    tl = p['title'].split('\n')
    if len(tl) > 2:
        errs.append('title は2行まで')
    for l in tl:
        if zlen(l) > 13.5:
            errs.append(f'title「{l}」が長い（1行13字まで）')
    sc = p.get('scenes', [])
    if not 3 <= len(sc) <= 5:
        errs.append(f'場面数 {len(sc)}（3〜5）')
    tot = sum(s.get('dur', 4.5) for s in sc) + LOOP
    if not 14 <= tot <= 26:
        errs.append(f'尺 {tot:.1f}秒（14〜26秒）')
    for i, s in enumerate(sc):
        if s['kind'] not in KINDS:
            errs.append(f'場面{i+1}: kind {s["kind"]}')
        sl = s['sub'].split('\n')
        if len(sl) > 2:
            errs.append(f'場面{i+1}: 字幕は2行まで')
        for l in sl:
            if zlen(l) > 16.5:
                errs.append(f'場面{i+1}: 字幕「{l}」が長い（16字まで）')
        if zlen(s.get('head', '')) > 17.5:
            errs.append(f'場面{i+1}: head が長い（17字まで）')
        if s['kind'] == 'steps':
            for it in s['data']['items']:
                if zlen(it) > 14.5:
                    errs.append(f'場面{i+1}: steps「{it}」が長い（14字まで）')
        if s['kind'] == 'bars' and len(s['data']['items']) > 4:
            errs.append(f'場面{i+1}: bars は4本まで')
    if len(p['caption']) > 2200:
        errs.append('キャプションが2200字を超えています')
    return errs


# ---------- 描画部品 ----------
def background(acc):
    im = Image.new('RGB', (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        c = (int(14 * (1 - t) + 3 * t), int(22 * (1 - t) + 4 * t), int(48 * (1 - t) + 10 * t))
        d.line([(0, y), (W, y)], fill=c)
    glow = Image.new('RGB', (W, H), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse([140, -380, 940, 420], fill=tuple(int(a * 0.28) for a in acc))
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    im = Image.fromarray(__import__('numpy').minimum(
        __import__('numpy').asarray(im, dtype='int16') + __import__('numpy').asarray(glow, dtype='int16'), 255).astype('uint8'))
    g = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(g)
    hz, vy = 1270, 1000  # 床のグリッド（消失点 y=1000）
    for i in range(12):
        y = hz + (H - hz) * ((i / 11) ** 1.8)
        gd.line([(0, y), (W, y)], fill=acc + (int(26 + 40 * i / 11),), width=2)
    for i in range(-10, 21):
        xb = W / 2 + (i - 5) * 150
        x_top = W / 2 + (xb - W / 2) * (hz - vy) / (H - vy)
        gd.line([(x_top, hz), (xb, H)], fill=acc + (40,), width=2)
    im = im.convert('RGBA')
    im.alpha_composite(g)
    return im


def text_c(d, im, s, font, cx, cy, fill):
    w = line_width(s, font)
    bb = font.getbbox('漢')
    draw_line(im, d, s, font, cx - w / 2, cy - (bb[1] + bb[3]) / 2, fill)


def rgba(c, a):
    return tuple(c[:3]) + (int(255 * max(0, min(1, a))),)


def glow_compose(base, layer, radius=14):
    g = layer.filter(ImageFilter.GaussianBlur(radius))
    base.alpha_composite(g)
    base.alpha_composite(g)
    base.alpha_composite(layer)


# ---------- 各場面の図（t は場面内の秒、9999 なら完成形） ----------
def draw_countdown(L, d, data, t, acc):
    a, b = data['from'], data['to']
    v = round(a + (b - a) * ease(t / 1.6))
    unit = data.get('unit', '日')
    nf, uf = F('Black', 230), F('Black', 80)
    nw, uw = nf.getlength(str(v)), uf.getlength(unit)
    x0 = W / 2 - (nw + 12 + uw) / 2
    d.text((x0, 840), str(v), font=nf, fill=rgba(acc, 1), anchor='ls')
    d.text((x0 + nw + 12, 840), unit, font=uf, fill=rgba(acc, 1), anchor='ls')
    # 時間の帯（今日 → 本番）
    p = ease((t - 0.3) / 1.3)
    x1, x2, y = 140, 940, 1040
    d.rounded_rectangle([x1, y - 10, x2, y + 10], 10, fill=rgba(acc, 0.22))
    d.rounded_rectangle([x1, y - 10, x1 + (x2 - x1) * p, y + 10], 10, fill=rgba(acc, 0.95))
    d.ellipse([x2 - 22, y - 22, x2 + 22, y + 22], fill=rgba(RED, 1))
    lf = F('Bold', 38)
    d.text((x1, y + 50), data.get('left', '今日'), font=lf, fill=(235, 240, 255, 255), anchor='lt')
    d.text((x2, y + 50), data.get('right', '本番'), font=lf, fill=rgba(RED, 1), anchor='rt')


def draw_bars(L, d, data, t, acc):
    items = data['items']
    vmax = max(i['value'] for i in items)
    lf, vf = F('Bold', 40), F('Black', 44)
    x0, x1 = 120, 860
    for k, it in enumerate(items):
        y = 600 + k * 165
        p = ease((t - 0.45 * k) / 0.6)
        c = RED if it.get('hl') else acc
        d.text((x0, y), it['label'], font=lf, fill=(235, 240, 255, 255), anchor='lb')
        d.rounded_rectangle([x0, y + 18, x1, y + 78], 14, fill=rgba(c, 0.15))
        if p > 0:
            d.rounded_rectangle([x0, y + 18, x0 + max(28, (x1 - x0) * it['value'] / vmax * p), y + 78], 14, fill=rgba(c, 0.95))
        if p > 0.05:
            d.text((x1 + 20, y + 48), f"{round(it['value'] * p)}{it.get('unit', '')}", font=vf, fill=rgba(c, 1), anchor='lm')


def draw_steps(L, d, data, t, acc):
    items = data['items']
    n = len(items)
    bh, gap = 140, 70
    top = 520 + (730 - (n * bh + (n - 1) * gap)) / 2
    tf, nf = F('Bold', 48), F('Black', 52)
    for k, it in enumerate(items):
        p = ease((t - 0.7 * k) / 0.45)
        if p <= 0:
            continue
        y = top + k * (bh + gap) - 60 * (1 - p)
        d.rounded_rectangle([110, y, 970, y + bh], 22, fill=(10, 18, 40, int(230 * p)), outline=rgba(acc, p), width=5)
        d.ellipse([140, y + 30, 220, y + 110], fill=rgba(acc, p))
        d.text((180, y + 70), str(k + 1), font=nf, fill=(10, 18, 40, int(255 * p)), anchor='mm')
        draw_line(L, d, it, tf, 250, y + 70 - (tf.getbbox('漢')[1] + tf.getbbox('漢')[3]) / 2, (255, 255, 255, int(255 * p)))
        if k < n - 1 and t > 0.7 * k + 0.4:
            q = ease((t - 0.7 * k - 0.4) / 0.3)
            ay = y + bh + 8
            d.line([(540, ay), (540, ay + (gap - 16) * q)], fill=rgba(acc, 1), width=6)
            if q > 0.9:
                d.polygon([(522, ay + gap - 30), (558, ay + gap - 30), (540, ay + gap - 10)], fill=rgba(acc, 1))


def draw_boxes(L, d, data, t, acc):
    n, fill = data['n'], data['fill']
    labels = data.get('labels', [])
    cols = min(n, 5)
    rows = math.ceil(n / cols)
    bw, gap = 160, 26
    top = 560 + (560 - (rows * bw + (rows - 1) * gap)) / 2
    lf = F('Bold', 36)
    lit = 0
    for k in range(n):
        r, c = divmod(k, cols)
        in_row = min(cols, n - r * cols)
        x = W / 2 - (in_row * bw + (in_row - 1) * gap) / 2 + c * (bw + gap)
        y = top + r * (bw + gap)
        on = k < fill and t >= 0.3 + 0.18 * k
        lit += on
        if on:
            d.rounded_rectangle([x, y, x + bw, y + bw], 20, fill=rgba(acc, 0.9))
        else:
            d.rounded_rectangle([x, y, x + bw, y + bw], 20, outline=rgba(acc, 0.45), width=4)
        if k < len(labels):
            d.text((x + bw / 2, y + bw / 2), labels[k], font=lf,
                   fill=(10, 18, 40, 255) if on else (220, 228, 250, 200), anchor='mm')
    if data.get('counter_unit'):
        cf = F('Black', 96)
        d.text((W / 2, 1200), f"{lit}{data['counter_unit']}", font=cf, fill=rgba(acc, 1), anchor='mm')


DRAW = {'countdown': draw_countdown, 'bars': draw_bars, 'steps': draw_steps, 'boxes': draw_boxes}


def draw_sub(L, d, text, alpha=1.0):
    f = F('Bold', 52)
    lines = text.split('\n')
    w = max(line_width(l, f) for l in lines) + 80
    h = len(lines) * 72 + 50
    d.rounded_rectangle([W / 2 - w / 2, SUB_CY - h / 2, W / 2 + w / 2, SUB_CY + h / 2], 18, fill=(0, 0, 0, int(165 * alpha)))
    for i, l in enumerate(lines):
        text_c(d, L, l, f, W / 2, SUB_CY - (len(lines) - 1) * 36 + i * 72, (255, 255, 255, int(255 * alpha)))


def draw_hook(L, d, title, alpha=1.0):
    f = F('Bold', 76)
    lines = title.split('\n')
    lh = int(76 * 1.3)
    for i, l in enumerate(lines):
        text_c(d, L, l, f, W / 2, HOOK_CY - (len(lines) - 1) * lh / 2 + i * lh, (255, 255, 255, int(255 * alpha)))


def frame(p, bg, t, total, starts):
    acc = ACCENT[p['account']]
    im = bg.copy()
    L = Image.new('RGBA', (W, H), (0, 0, 0, 0))   # 文字など（グローなし）
    G = Image.new('RGBA', (W, H), (0, 0, 0, 0))   # 図（グローあり）
    d, gd = ImageDraw.Draw(L), ImageDraw.Draw(G)
    scenes = p['scenes']
    loop_start = total - LOOP
    if t >= loop_start:   # 最後：場面1の完成形＋フック＋CTA
        s0 = scenes[0]
        DRAW[s0['kind']](G, gd, s0['data'], 9999, acc)
        draw_hook(L, d, p['title'])
        draw_sub(L, d, CTA, ease((t - loop_start) / 0.4))
    else:
        k = max(i for i, st in enumerate(starts) if st <= t)
        s = scenes[k]
        lt = t - starts[k]
        DRAW[s['kind']](G, gd, s['data'], lt, acc)
        if k == 0:
            draw_hook(L, d, p['title'])
        elif s.get('head'):
            text_c(d, L, s['head'], F('Bold', 56), W / 2, HEAD_CY, (255, 255, 255, int(255 * ease(lt / 0.35))))
        draw_sub(L, d, s['sub'])
    glow_compose(im, G)
    im.alpha_composite(L)
    # 進捗バーとブランド
    od = ImageDraw.Draw(im)
    od.rectangle([0, 0, W * t / total, 7], fill=rgba(acc, 1))
    draw_brand(im)
    return im.convert('RGB')


def draw_brand(im, x=36, y=30, size=96):
    """左上に塾のロゴ（白い丸の中の狼のマーク）と塾名"""
    if size not in _LOGO:
        _LOGO[size] = Image.open(LOGO).convert('RGBA').resize((size, size), Image.LANCZOS)
    im.alpha_composite(_LOGO[size], (x, y))
    od = ImageDraw.Draw(im)
    od.text((x + size + 18, y + size / 2), BRAND, font=F('SemiBold', 34), fill=(236, 240, 248, 255), anchor='lm')


def timeline(p):
    starts, acc = [], 0.0
    for s in p['scenes']:
        starts.append(acc)
        acc += s.get('dur', 4.5)
    return starts, acc + LOOP


def pick_bgm(p, bgm_dir, idx):
    if p['account'] == '保護者':
        return PARENT_BGM
    sb = sorted(f for f in os.listdir(bgm_dir) if f.endswith('.m4a') and f != PARENT_BGM)
    y, m, dd = map(int, p['datetime'][:10].split('/'))
    return sb[(date(y, m, dd).toordinal() * 2 + 2 + idx) % len(sb)]  # 同じ日のQ&A(+0,+1)と重ならないように


def render(p, repo, bgm_dir, idx=0, frames_dir=None, frame_times=()):
    errs = check(p)
    if errs:
        raise SystemExit(f'{p["key"]}: ' + ' / '.join(errs))
    starts, total = timeline(p)
    bg = background(ACCENT[p['account']])
    out = os.path.join(repo, 'videos', p['key'] + '.mp4')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bgm = pick_bgm(p, bgm_dir, idx) if bgm_dir else None
    n = int(round(total * FPS))
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
           '-r', str(FPS), '-i', '-']
    if bgm:
        cmd += ['-stream_loop', '-1', '-i', os.path.join(bgm_dir, bgm),
                '-filter_complex', f'[1:a]atrim=0:{total:.3f},asetpts=N/SR/TB,volume=0.8,afade=t=in:d=0.3,'
                                   f'afade=t=out:st={total-0.8:.2f}:d=0.8[a]', '-map', '0:v', '-map', '[a]']
    else:
        cmd += ['-f', 'lavfi', '-t', f'{total:.3f}', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100',
                '-map', '0:v', '-map', '1:a']
    cmd += ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
            '-b:a', '160k', '-ar', '44100', '-t', f'{total:.3f}', '-movflags', '+faststart', out]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        pr.stdin.write(frame(p, bg, i / FPS, total, starts).tobytes())
    pr.stdin.close()
    if pr.wait():
        raise SystemExit('ffmpeg 失敗: ' + p['key'])
    if frames_dir:
        os.makedirs(frames_dir, exist_ok=True)
        ts = list(frame_times) or check_times(p)
        for tt in ts:
            frame(p, bg, tt, total, starts).save(os.path.join(frames_dir, f'{p["key"]}_{tt:05.2f}.png'))
    return out, bgm, total


def check_times(p):
    """仕様書9の確認コマ：0.5秒／各場面の開始+0.5秒と終了-0.3秒／最後の0.5秒手前"""
    starts, total = timeline(p)
    ts = [0.5]
    for s, st in zip(p['scenes'], starts):
        ts += [st + 0.5, st + s.get('dur', 4.5) - 0.3]
    ts.append(total - 0.5)
    return sorted(set(round(x, 2) for x in ts))


if __name__ == '__main__':
    args = sys.argv[1:]
    opts = {}
    for k in ('--bgm-dir', '--frames-dir'):
        if k in args:
            i = args.index(k); opts[k] = args[i + 1]; del args[i:i + 2]
    posts_path, repo = args
    posts = json.load(open(posts_path, encoding='utf-8'))
    errs = [f'{p["key"]}: {e}' for p in posts for e in check(p)]
    if errs:
        raise SystemExit('チェックに失敗:\n' + '\n'.join(errs))
    by_day = {}
    s_idx = 0
    for p in posts:
        out, bgm, total = render(p, repo, opts.get('--bgm-dir'), s_idx, opts.get('--frames-dir'))
        if p['account'] == '受験生':
            s_idx += 1
        print(f'OK {out} {total:.1f}秒 bgm={bgm}')
        item = {k: p[k] for k in ('key', 'datetime', 'account', 'title', 'caption')}
        item.update(type='図解アニメ', video=f'videos/{p["key"]}.mp4', bgm=(bgm or '').replace('.m4a', ''))
        by_day.setdefault(p['datetime'][:10].replace('/', '-'), []).append(item)
    for day, items in by_day.items():
        qp = os.path.join(repo, 'queue', f'{day}.json')
        cur = json.load(open(qp, encoding='utf-8')) if os.path.exists(qp) else []
        keys = {i['key'] for i in items}
        cur = [c for c in cur if c['key'] not in keys] + items
        with open(qp, 'w', encoding='utf-8') as f:
            json.dump(cur, f, ensure_ascii=False, indent=1)
        print(f'queue/{day}.json: {len(cur)}件')
