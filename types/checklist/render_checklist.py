#!/usr/bin/env python3
"""
チェックリスト一枚型リールの生成。仕様は Notion「仕様書｜チェックリスト一枚型」。
（分析タスクの版はくろさんのPCにあり、この環境から届かないため、2026-11-14夜に仕様書から作り直したもの）
  python3 types/checklist/render_checklist.py posts.json REPO_DIR --bgm-dir BGM_DIR [--broll-dir DIR] [--frames-dir DIR]
posts の各要素: key, datetime("YYYY/MM/DD HH:MM"), account(保護者/受験生), pattern(A/B/C), grade,
  label, title(見出し。\\n で2行まで), items: [{"m": "ok"|"ng", "t": "項目(\\n で2行まで)"}], summary(\\n で2行まで), caption
  ok=✓（やること）, ng=○（落とし穴）
出力: REPO_DIR/videos/<key>.mp4（8.0秒）、REPO_DIR/queue/<投稿日>.json に追記（同じ key 以外は消さない。proto_ は入れない）
"""
import json, os, subprocess, sys, tempfile
from datetime import date
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, REPO_ROOT)
from render_qa import draw_line, line_width  # 絵文字つきの行の描画を共用

W, H, FPS, DUR = 1080, 1920, 30, 8.0
FD = '/usr/share/fonts/opentype/noto/'
def F(w, s):
    return ImageFont.truetype(FD + f'NotoSansCJK-{w}.ttc', s, index=0)  # index0 = JP

PX0, PX1, PY0, PY1 = 90, 990, 300, 1560
YELLOW = (246, 190, 40)
SUM_C = (255, 226, 120)
GRAY = (170, 170, 176)
LGRAY = (200, 200, 206)
BRAND = '現役医大生塾 MedWolf'
LOGO = os.path.join(REPO_ROOT, 'assets', 'brand', 'medwolf_badge.png')
CTA = '保存して見返してね👉 詳しくはキャプション'
LEGEND = '✓＝やること　○＝落とし穴'
PARENT_BGM = 'In-Between.m4a'
CTA_WORDS = ('プロフのリンク', '@')
FACE_FREE = {'IMG_9531.mp4', 'IMG_9753.mp4'}


def zlen(s):
    return sum(0.5 if ord(c) < 0x2000 else 1 for c in s)


def check(p):
    e = []
    for k in ('key', 'datetime', 'account', 'pattern', 'label', 'title', 'items', 'summary', 'caption'):
        if not p.get(k):
            e.append(f'{k} がない')
    if e:
        return e
    if p['pattern'] not in ('A', 'B', 'C'):
        e.append('pattern は A/B/C')
    if zlen(p['label']) > 14:
        e.append(f'label「{p["label"]}」が長い（14字まで）')
    tl = p['title'].split('\n')
    if len(tl) > 2 or any(zlen(l) > 13 for l in tl):
        e.append('見出しは2行・1行13字まで')
    it = p['items']
    if not 6 <= len(it) <= 8:
        e.append(f'項目数 {len(it)}（6〜8）')
    ms = {i['m'] for i in it}
    if ms != {'ok', 'ng'}:
        e.append('✓と○の両方が必要')
    nl = 0
    for i in it:
        ls = i['t'].split('\n'); nl += len(ls)
        if len(ls) > 2 or any(zlen(l) > 16 for l in ls):
            e.append(f'項目「{i["t"]}」は2行・1行16字まで')
    if nl > 13:
        e.append(f'項目の行数合計 {nl}（13まで）')
    sl = p['summary'].split('\n')
    if len(sl) > 2 or any(zlen(l) > 17 for l in sl):
        e.append('まとめは2行・1行17字まで')
    if not all(w in p['caption'] for w in CTA_WORDS):
        e.append('キャプションにCTAがない')
    if len(p['caption']) > 2200:
        e.append('キャプションが2200字を超える')
    return e


# ---------- レイアウト ----------
F_LABEL, F_HEAD, F_LEG, F_ITEM, F_SUM, F_CTA, F_BRAND = (F('Medium', 34), F('Black', 62), F('Regular', 30),
                                                         F('Medium', 40), F('Bold', 42), F('Regular', 32), F('Medium', 30))
PAD = 54
ITEM_LH = 52
ITEM_GAP = 18


def layout_height(p):
    h = PAD + 44 + 30            # ラベル
    h += len(p['title'].split('\n')) * 80 + 14
    h += 42 + 26                 # 凡例
    for i in p['items']:
        h += len(i['t'].split('\n')) * ITEM_LH + ITEM_GAP
    h += 20 + 2 + 30             # 区切り線
    h += len(p['summary'].split('\n')) * 58 + 26
    h += 44 + PAD                # CTA
    return h


def draw_mark(d, kind, x, cy):
    r = 19
    if kind == 'ok':
        d.ellipse((x, cy - r, x + 2 * r, cy + r), fill=YELLOW)
        d.line([(x + 10, cy + 1), (x + 17, cy + 9), (x + 30, cy - 8)], fill=(10, 10, 10), width=6, joint='curve')
    else:
        d.ellipse((x + 2, cy - r + 2, x + 2 * r - 2, cy + r - 2), outline=(255, 255, 255), width=4)


def panel_layer(p):
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ph = layout_height(p)
    top = PY0 + max(0, (PY1 - PY0 - ph) // 2)
    bot = top + ph
    if bot > PY1:
        raise SystemExit(f'{p["key"]}: パネルが y={bot} まで伸びて {PY1} を超える')
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((PX0, top, PX1, bot), radius=18, fill=(8, 8, 10, 237))
    # ブランド名（パネルの上44px）
    bw = line_width(BRAND, F_BRAND)
    d.text(((W - bw) // 2, top - 44 - 30), BRAND, font=F_BRAND, fill=(255, 255, 255))
    # ロゴ（右上52px）
    if os.path.exists(LOGO):
        lg = Image.open(LOGO).convert('RGBA').resize((52, 52), Image.LANCZOS)
        im.alpha_composite(lg, (PX1 - PAD - 52 + 20, top + PAD - 14))
    x = PX0 + PAD
    y = top + PAD
    d.text((x, y), p['label'], font=F_LABEL, fill=LGRAY)
    y += 44 + 30
    for l in p['title'].split('\n'):
        draw_line(im, d, l, F_HEAD, x, y, (255, 255, 255))
        y += 80
    y += 14
    d.text((x, y), LEGEND, font=F_LEG, fill=GRAY)
    y += 42 + 26
    for it in p['items']:
        ls = it['t'].split('\n')
        draw_mark(d, it['m'], x, y + 26)
        for j, l in enumerate(ls):
            draw_line(im, d, l, F_ITEM, x + 58, y + j * ITEM_LH, (255, 255, 255))
        y += len(ls) * ITEM_LH + ITEM_GAP
    y += 20
    d.line([(x, y), (PX1 - PAD, y)], fill=(90, 90, 96), width=2)
    y += 2 + 30
    for l in p['summary'].split('\n'):
        draw_line(im, d, l, F_SUM, x, y, SUM_C)
        y += 58
    y += 26
    cw = line_width(CTA, F_CTA)
    draw_line(im, d, CTA, F_CTA, (W - cw) // 2, y, LGRAY)
    return im


def pick_broll(p, broll_dir, idx):
    clips = sorted(f for f in os.listdir(broll_dir) if f.lower().endswith(('.mp4', '.mov')))
    # 顔（あご・口元）が写りにくい素材を優先（2026-11-14 目視で選定）
    safe = [c for c in clips if c in FACE_FREE]
    clips = safe or clips
    y, m, dd = map(int, p['datetime'][:10].split('/'))
    clip = clips[(date(y, m, dd).toordinal() + idx * 3) % len(clips)]
    path = os.path.join(broll_dir, clip)
    dur = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                         '-of', 'csv=p=0', path]).decode().strip() or 0)
    start = max(0.0, min(2.0, dur - DUR - 0.2))
    return path, start


def pick_bgm(p, bgm_dir, idx):
    if p['account'] == '保護者':
        return PARENT_BGM
    sb = sorted(f for f in os.listdir(bgm_dir) if f.endswith('.m4a') and f != PARENT_BGM)
    y, m, dd = map(int, p['datetime'][:10].split('/'))
    return sb[(date(y, m, dd).toordinal() * 2 + 2 + idx) % len(sb)]  # 同じ日のQ&A(+0,+1)と重ならないように


def render(p, repo, bgm_dir, broll_dir, idx=0, frames_dir=None):
    errs = check(p)
    if errs:
        raise SystemExit(f'{p["key"]}: ' + ' / '.join(errs))
    tmpd = tempfile.mkdtemp()
    pp = os.path.join(tmpd, 'panel.png')
    panel_layer(p).save(pp)
    src, st = pick_broll(p, broll_dir, idx)
    out = os.path.join(repo, 'videos', p['key'] + '.mp4')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    T = f'{DUR:.3f}'
    bgm = pick_bgm(p, bgm_dir, idx) if bgm_dir else None
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{st:.2f}', '-t', T, '-i', src,
           '-loop', '1', '-t', T, '-framerate', str(FPS), '-i', pp]
    vf = (f"[0:v]scale=-2:{H},crop={W}:{H},setsar=1,fps={FPS},boxblur=6:1,"
          f"eq=brightness=-0.12:saturation=0.8[b];[b][1:v]overlay=0:0,format=yuv420p[v]")
    if bgm:
        cmd += ['-i', os.path.join(bgm_dir, bgm)]
        af = f"[2:a]atrim=0:{T},asetpts=N/SR/TB,volume=0.8,afade=t=out:st={DUR-0.6:.2f}:d=0.6[a]"
    else:
        cmd += ['-f', 'lavfi', '-t', T, '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100']
        af = '[2:a]anull[a]'
    cmd += ['-filter_complex', vf + ';' + af, '-map', '[v]', '-map', '[a]', '-frames:v', str(int(DUR * FPS)),
            '-t', T, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-r', str(FPS),
            '-c:a', 'aac', '-b:a', '160k', '-ar', '44100', '-movflags', '+faststart', out]
    subprocess.run(cmd, check=True)
    os.unlink(pp); os.rmdir(tmpd)
    if frames_dir:
        os.makedirs(frames_dir, exist_ok=True)
        for tt in (0.3, 4.0, 7.7):
            subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(tt), '-i', out, '-frames:v', '1',
                            os.path.join(frames_dir, f'{p["key"]}_{tt:04.1f}.png')], check=True)
    return out, bgm


if __name__ == '__main__':
    args = sys.argv[1:]
    opts = {}
    for k in ('--bgm-dir', '--frames-dir', '--broll-dir'):
        if k in args:
            i = args.index(k); opts[k] = args[i + 1]; del args[i:i + 2]
    posts_path, repo = args
    broll = opts.get('--broll-dir') or os.path.join(repo, 'assets', 'broll')
    posts = json.load(open(posts_path, encoding='utf-8'))
    errs = [f'{p.get("key")}: {e}' for p in posts for e in check(p)]
    if errs:
        raise SystemExit('チェックに失敗:\n' + '\n'.join(errs))
    by_day, s_idx = {}, 0
    for n, p in enumerate(posts):
        out, bgm = render(p, repo, opts.get('--bgm-dir'), broll, s_idx if p['account'] == '受験生' else n,
                          opts.get('--frames-dir'))
        if p['account'] == '受験生':
            s_idx += 1
        print(f'OK {out} bgm={bgm}')
        if p['key'].startswith('proto_'):
            continue
        item = {k: p[k] for k in ('key', 'datetime', 'account', 'title', 'caption')}
        item.update(type='チェックリスト一枚', pattern=p['pattern'], grade=p.get('grade', ''),
                    video=f'videos/{p["key"]}.mp4', bgm=(bgm or '').replace('.m4a', ''))
        by_day.setdefault(p['datetime'][:10].replace('/', '-'), []).append(item)
    for day, items in by_day.items():
        qp = os.path.join(repo, 'queue', f'{day}.json')
        cur = json.load(open(qp, encoding='utf-8')) if os.path.exists(qp) else []
        keys = {i['key'] for i in items}
        cur = [c for c in cur if c['key'] not in keys] + items
        with open(qp, 'w', encoding='utf-8') as f:
            json.dump(cur, f, ensure_ascii=False, indent=1)
        print(f'queue/{day}.json: {len(cur)}件')
