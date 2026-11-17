#!/usr/bin/env python3
"""
決め絵＋NG○選タイトル型リールの生成。仕様は Notion「仕様書｜決め絵＋NG○選タイトル型」。
（分析タスク版はくろさんのPCにあり、この環境から届かないため、2026-11-17夜に仕様書から作り直したもの）
  python3 types/ng_title/render_ng.py posts.json REPO_DIR --bgm-dir BGM_DIR [--broll-dir DIR] [--frames-dir DIR]
posts の各要素: key, datetime("YYYY/MM/DD HH:MM"), account(保護者/受験生), pattern(A/B/C), grade,
  kicker(10字まで), topic(\\n で2行・1行8字まで), ng(7字まで), lead(20字まで), caption
出力: REPO_DIR/videos/<key>.mp4（8.0秒。BGMはループしない）、REPO_DIR/queue/<投稿日>.json に追記（type=NGタイトル。proto_ は入れない）
"""
import json, os, subprocess, sys, tempfile
from datetime import date
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))

W, H, FPS, DUR = 1080, 1920, 30, 8.0  # 2026-11-17 くろさん指定で10秒→8秒（BGMが8秒のため）
FD = '/usr/share/fonts/opentype/noto/'
def F(w, s):
    return ImageFont.truetype(FD + f'NotoSansCJK-{w}.ttc', s, index=0)

YELLOW = (255, 214, 64)
WHITE = (255, 255, 255)
BRAND = '現役医大生塾 MedWolf'
SUB2 = '内容はキャプションに書いています'
SUB3 = '保存して、あとで読んでみてね'
SUB_T = (3.7, 5.2, 6.7)
TITLE_END = 3.5
PARENT_BGM = 'In-Between.m4a'
CTA_WORDS = ('公式LINE', '@')
BG_CLIPS = ('IMG_9531.mp4', 'IMG_9753.mp4')  # 顔の写らない素材を交互に
F_KICK, F_TOPIC, F_NG, F_SUB, F_BRAND = F('Bold', 64), F('Black', 118), F('Black', 150), F('Bold', 46), F('Medium', 30)
MAXW = W - 40


def zlen(s):
    return sum(0.5 if ord(c) < 0x2000 else 1 for c in s)


def check(p):
    e = []
    for k in ('key', 'datetime', 'account', 'pattern', 'kicker', 'topic', 'ng', 'lead', 'caption'):
        if not p.get(k):
            e.append(f'{k} がない')
    if e:
        return e
    if p['pattern'] not in ('A', 'B', 'C'):
        e.append('pattern は A/B/C')
    if zlen(p['kicker']) > 10:
        e.append(f'kicker「{p["kicker"]}」が長い（10字まで）')
    tl = p['topic'].split('\n')
    if len(tl) > 2 or any(zlen(l) > 8 for l in tl):
        e.append('topic は2行・1行8字まで')
    if zlen(p['ng']) > 7:
        e.append(f'ng「{p["ng"]}」が長い（7字まで）')
    if zlen(p['lead']) > 20:
        e.append(f'lead「{p["lead"]}」が長い（20字まで）')
    if not all(w in p['caption'] for w in CTA_WORDS):
        e.append('キャプションに公式LINEの案内（公式LINE・@）がない')
    if len(p['caption']) > 2200:
        e.append('キャプションが2200字を超える')
    return e


def tw(d, s, f, sw=0):
    b = d.textbbox((0, 0), s, font=f, stroke_width=sw)
    return b[2] - b[0]


def title_layer(p):
    lines = [('＼' + p['kicker'] + '／', F_KICK, YELLOW, 92)]
    lines += [(l, F_TOPIC, WHITE, 140) for l in p['topic'].split('\n')]
    lines += [(p['ng'], F_NG, YELLOW, 176)]
    total = sum(lh for *_, lh in lines)
    y = 760 - total // 2
    txt = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(txt)
    for s, f, c, lh in lines:
        w = tw(d, s, f, 8)
        if w > MAXW:
            raise SystemExit(f'{p["key"]}: 大タイトル「{s}」が横にはみ出す（{w}px）')
        d.text((W // 2, y + lh // 2), s, font=f, fill=c, anchor='mm', stroke_width=8, stroke_fill=(0, 0, 0))
        y += lh
    if y > 1150 or 760 - total // 2 < 480:
        raise SystemExit(f'{p["key"]}: 大タイトルが上25%か字幕の位置にかかる')
    sh = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    a = txt.split()[3].filter(ImageFilter.GaussianBlur(14))
    sh.putalpha(a.point(lambda v: int(v * 0.75)))
    sh.alpha_composite(txt)
    return sh


def sub_layer(s, i, key):
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = tw(d, s, F_SUB)
    if w + 64 > MAXW:
        raise SystemExit(f'{key}: 字幕「{s}」が横にはみ出す')
    y = 1180 + i * 96
    d.rounded_rectangle(((W - w) // 2 - 32, y, (W + w) // 2 + 32, y + 76), radius=20, fill=(0, 0, 0, 150))
    d.text((W // 2, y + 38), s, font=F_SUB, fill=WHITE, anchor='mm')
    return im


def brand_layer():
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = tw(d, BRAND, F_BRAND, 3)
    d.text(((W - w) // 2, 1560), BRAND, font=F_BRAND, fill=WHITE, stroke_width=3, stroke_fill=(0, 0, 0))
    return im

def bgm_duration(path):
    return float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                          '-of', 'csv=p=0', path]).decode().strip() or 0)


def check_bgm_length(path, need):
    """BGMはループさせない（つなぎ目で曲が不自然に戻るため。2026-11-17くろさん指定）。足りなければ止める"""
    d = bgm_duration(path)
    if d + 0.01 < need:
        raise SystemExit(f'BGM {os.path.basename(path)} は {d:.1f}秒で、動画 {need:.1f}秒に足りない。'
                         'ループはしないので、動画を短くするか長いBGMを用意する')


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
    layers = [title_layer(p), brand_layer()] + [sub_layer(s, i, p['key']) for i, s in enumerate((p['lead'], SUB2, SUB3))]
    paths = []
    for i, L in enumerate(layers):
        pp = os.path.join(tmpd, f'l{i}.png'); L.save(pp); paths.append(pp)
    y, m, dd = map(int, p['datetime'][:10].split('/'))
    clip = BG_CLIPS[(date(y, m, dd).toordinal() + idx) % 2]
    src = os.path.join(broll_dir, clip)
    out = os.path.join(repo, 'videos', p['key'] + '.mp4')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    T = f'{DUR:.3f}'
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-stream_loop', '-1', '-ss', '1.0', '-t', T, '-i', src]
    for pp in paths:
        cmd += ['-loop', '1', '-t', T, '-framerate', str(FPS), '-i', pp]
    bgm = pick_bgm(p, bgm_dir, idx) if bgm_dir else None
    na = 1 + len(paths)
    if bgm:
        check_bgm_length(os.path.join(bgm_dir, bgm), DUR)
        cmd += ['-i', os.path.join(bgm_dir, bgm)]
        af = f"[{na}:a]atrim=0:{T},asetpts=N/SR/TB,volume=0.8,afade=t=out:st={DUR-0.6:.2f}:d=0.6[a]"
    else:
        cmd += ['-f', 'lavfi', '-t', T, '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100']
        af = f'[{na}:a]anull[a]'
    vf = (f"[0:v]scale=-2:{H},crop={W}:{H},setsar=1,fps={FPS},eq=brightness=-0.10:saturation=0.9[b0];"
          f"[b0][1:v]overlay=0:0:enable='lt(t,{TITLE_END})'[b1];[b1][2:v]overlay=0:0[b2];"
          f"[b2][3:v]overlay=0:0:enable='gte(t,{SUB_T[0]})'[b3];"
          f"[b3][4:v]overlay=0:0:enable='gte(t,{SUB_T[1]})'[b4];"
          f"[b4][5:v]overlay=0:0:enable='gte(t,{SUB_T[2]})',format=yuv420p[v]")
    cmd += ['-filter_complex', vf + ';' + af, '-map', '[v]', '-map', '[a]', '-frames:v', str(int(DUR * FPS)),
            '-t', T, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-r', str(FPS),
            '-c:a', 'aac', '-b:a', '160k', '-ar', '44100', '-movflags', '+faststart', out]
    subprocess.run(cmd, check=True)
    for pp in paths:
        os.unlink(pp)
    os.rmdir(tmpd)
    if frames_dir:
        os.makedirs(frames_dir, exist_ok=True)
        for tt in (0.3, 3.0, 4.0, 5.5, 7.7):
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
    by_day = {}
    for n, p in enumerate(posts):
        out, bgm = render(p, repo, opts.get('--bgm-dir'), broll, n, opts.get('--frames-dir'))
        print(f'OK {out} bgm={bgm}')
        if p['key'].startswith('proto_'):
            continue
        item = {k: p[k] for k in ('key', 'datetime', 'account', 'caption')}
        item.update(title=p['kicker'] + '\n' + p['topic'].replace('\n', '') + '\n' + p['ng'],
                    type='NGタイトル', pattern=p['pattern'], grade=p.get('grade', ''),
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
