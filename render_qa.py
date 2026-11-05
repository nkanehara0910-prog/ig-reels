#!/usr/bin/env python3
"""
「現役医大生しゅうが質問答えます」型 8秒リールの自動生成（これまでの投稿と同じレイアウト）

レイアウト（1080x1920・黒背景）
  上段  : 【必見】＋タイトル（白・明朝・左寄せ）
  中段  : 実写の素材動画（横長に切り抜いて全幅で再生）
  カード: 黒ヘッダー「現役医大生しゅうが質問答えます💪」＋白地に質問文（黒・明朝）
  下段  : A.〜（白・明朝・回答のチラ見せ）

使い方:
  python3 render_qa.py posts.json broll_dir out_dir [--bgm music.mp3]
posts.json は [{key, account, title, question, answer, broll(任意), broll_start(任意)}...]
  title/answer は改行(\n)で行を指定。2行目以降は1字下げ（これまでの投稿と同じ）。
"""
import json, os, random, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont

W, H, DUR = 1080, 1920, 8
SERIF_MED = '/usr/share/fonts/opentype/noto/NotoSerifCJK-Medium.ttc'
SERIF_BOLD = '/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc'
SERIF_REG = '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc'
EMOJI = '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf'

BAND_Y, BAND_H = 680, 560          # 素材動画の帯
CARD_X, CARD_W, CARD_Y = 126, 474, 836
HEADER_H = 122
TITLE_X, TITLE_SIZE, TITLE_LH = 46, 60, 68
ANS_X, ANS_SIZE, ANS_LH, ANS_GAP = 94, 60, 74, 62
Q_SIZE, Q_LH, Q_PAD_X, Q_PAD_TOP, Q_PAD_BOTTOM = 36, 48, 40, 92, 58
HEADER_TEXT = '現役医大生しゅうが質問答えます'


def emoji_img(ch, size):
    f = ImageFont.truetype(EMOJI, 109)
    im = Image.new('RGBA', (136, 128), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((0, 0), ch, font=f, embedded_color=True)
    im = im.crop(im.getbbox())
    return im.resize((size, int(size * im.height / im.width)), Image.LANCZOS)


def draw_lines(d, lines, font, x, y, lh, fill, indent=True):
    for i, line in enumerate(lines):
        dx = font.size if (indent and i > 0) else 0
        d.text((x + dx, y + i * lh), line, font=font, fill=fill)


def overlay(post):
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # 上下の黒地（帯の外側）
    d.rectangle([0, 0, W, BAND_Y], fill=(0, 0, 0, 255))
    d.rectangle([0, BAND_Y + BAND_H, W, H], fill=(0, 0, 0, 255))

    # タイトル（帯の上端から逆算して下揃え）
    tf = ImageFont.truetype(SERIF_MED, TITLE_SIZE)
    tlines = ['【必見】'] + post['title'].split('\n')
    ty = BAND_Y - 46 - TITLE_LH * len(tlines)
    d.text((TITLE_X - 8, ty), tlines[0], font=tf, fill='white')
    draw_lines(d, tlines[1:], tf, TITLE_X - 14, ty + TITLE_LH, TITLE_LH, 'white')

    # 質問カード
    qf = ImageFont.truetype(SERIF_REG, Q_SIZE)
    qlines = post['question'].split('\n')
    card_h = HEADER_H + Q_PAD_TOP + Q_LH * len(qlines) + Q_PAD_BOTTOM
    d.rectangle([CARD_X, CARD_Y, CARD_X + CARD_W, CARD_Y + HEADER_H], fill=(0, 0, 0, 255))
    d.rectangle([CARD_X, CARD_Y + HEADER_H, CARD_X + CARD_W, CARD_Y + card_h], fill=(255, 255, 255, 255))
    hf = ImageFont.truetype(SERIF_BOLD, 27)
    hw = hf.getlength(HEADER_TEXT)
    em = emoji_img('💪', 30)
    hx = CARD_X + (CARD_W - hw - em.width - 4) / 2
    hy = CARD_Y + (HEADER_H - 27) / 2 - 6
    d.text((hx, hy), HEADER_TEXT, font=hf, fill='white')
    im.alpha_composite(em, (int(hx + hw + 4), int(hy + 4)))
    for i, line in enumerate(qlines):
        d.text((CARD_X + Q_PAD_X, CARD_Y + HEADER_H + Q_PAD_TOP + i * Q_LH), line, font=qf, fill=(20, 20, 20, 255))

    # 回答のチラ見せ
    af = ImageFont.truetype(SERIF_MED, ANS_SIZE)
    alines = post['answer'].split('\n')
    ay = max(CARD_Y + card_h, BAND_Y + BAND_H) + ANS_GAP
    draw_lines(d, alines, af, ANS_X - 14, ay, ANS_LH, 'white')
    return im


def pick_broll(post, broll_dir):
    if post.get('broll'):
        return os.path.join(broll_dir, post['broll']), float(post.get('broll_start', 0))
    clips = sorted(f for f in os.listdir(broll_dir) if f.lower().endswith(('.mp4', '.mov', '.m4v')))
    if not clips:
        raise SystemExit('素材フォルダに動画がありません: ' + broll_dir)
    clip = random.choice(clips)
    path = os.path.join(broll_dir, clip)
    dur = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                         '-of', 'csv=p=0', path]).decode().strip() or 0)
    start = random.uniform(0, max(0, dur - DUR - 0.5))
    return path, start


def render(post, broll_dir, out_dir, bgm=None):
    os.makedirs(out_dir, exist_ok=True)
    ov = overlay(post)
    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False).name
    ov.save(tmp)
    src, start = pick_broll(post, broll_dir)
    out = os.path.join(out_dir, post['key'] + '.mp4')
    vf = (f"[0:v]scale={W}:-2,crop={W}:{BAND_H},setsar=1,fps=30[b];"
          f"color=black:s={W}x{H}:d={DUR}:r=30[bg];"
          f"[bg][b]overlay=0:{BAND_Y}[v1];[v1][1:v]overlay=0:0,format=yuv420p[v]")
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{start:.2f}', '-t', str(DUR), '-i', src,
           '-loop', '1', '-t', str(DUR), '-i', tmp]
    if bgm == 'broll':  # 素材動画の環境音をそのまま使う
        cmd += ['-f', 'lavfi', '-t', str(DUR), '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100']
        amap = ['-map', '0:a?', '-af', f'afade=t=in:d=0.3,afade=t=out:st={DUR-0.5}:d=0.5']
    elif bgm:
        cmd += ['-i', bgm]
        amap = ['-map', '2:a', '-af', f'afade=t=out:st={DUR-0.6}:d=0.6']
    else:
        cmd += ['-f', 'lavfi', '-t', str(DUR), '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100']
        amap = ['-map', '2:a']
    cmd += ['-filter_complex', vf, '-map', '[v]'] + amap + [
        '-t', str(DUR), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-r', '30',
        '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', out]
    subprocess.run(cmd, check=True)
    os.unlink(tmp)
    return out


if __name__ == '__main__':
    args = sys.argv[1:]
    bgm = None
    if '--bgm' in args:
        i = args.index('--bgm'); bgm = args[i + 1]; del args[i:i + 2]
    posts_path, broll_dir, out_dir = args
    for p in json.load(open(posts_path, encoding='utf-8')):
        print('OK', render(p, broll_dir, out_dir, bgm))
