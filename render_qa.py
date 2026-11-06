#!/usr/bin/env python3
"""
「現役医大生しゅうが質問答えます」型 7秒リールの自動生成（実投稿の書き出し動画を実測して合わせたレイアウト）

レイアウト（1080x1920・黒背景）
  上段  : 【必見】＋タイトル（白・明朝Bold）。行は左揃え・字下げなし、ブロック全体を画面中央に配置
  中段  : 実写の素材動画（y=680〜1240 の帯）
  カード: x=126〜598。黒ヘッダー「現役医大生しゅうが質問答えます💪」＋白地（高さ固定 960〜1449）
          質問文は左揃え、ブロック全体をカードの中で上下左右中央に配置。行末の絵文字（🥲など）も描画
  下段  : 0〜4.23秒「A.〜」（ブロック中央・2行目は1字下げ）
          4.23〜4.57秒 何も出さない
          4.57秒〜 「詳細はキャプションをチェック✅」（中央）
  音    : BGM ＋ クリック音（0.07〜0.3秒に3回・4.62秒に2回。実投稿の音をそのまま使用）

使い方:
  python3 render_qa.py posts.json broll_dir out_dir [--bgm music.m4a] [--sfx clicks.m4a]
"""
import json, os, random, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FPS = 30
FRAMES = 211                      # 7.033秒（実投稿と同じ）
DUR = FRAMES / FPS
ANS_END = 127 / FPS               # 回答の表示終了
CTA_START = 137 / FPS             # 「詳細はキャプションをチェック」表示開始

FONT_DIR = '/usr/share/fonts/opentype/noto/'
SERIF = {w: FONT_DIR + f'NotoSerifCJK-{w}.ttc' for w in ('Regular', 'Medium', 'SemiBold', 'Bold', 'Black')}
EMOJI = '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf'

BAND_Y, BAND_H = 680, 560
CARD_X0, CARD_X1 = 126, 598
CARD_Y, HEADER_BOTTOM, CARD_BOTTOM = 836, 960, 1449
HEADER_TEXT = '現役医大生しゅうが質問答えます'

TITLE_FONT, TITLE_SIZE, TITLE_LH, TITLE_BOTTOM = SERIF['Bold'], 68, 68, 620
ANS_FONT, ANS_SIZE, ANS_LH, ANS_CY = SERIF["SemiBold"], 72, 75, 1561
CTA_FONT, CTA_SIZE, CTA_CY = SERIF['Medium'], 58, 1555
CTA_TEXT = '詳細はキャプションをチェック✅'
Q_FONT, Q_SIZES = SERIF["Regular"], (44, 42, 40, 38, 36, 34)
Q_MAX_W = CARD_X1 - CARD_X0 - 2 * 22
Q_MAX_H = CARD_BOTTOM - HEADER_BOTTOM - 2 * 50
TITLE_MAX_W = W - 2 * 40
ANS_MAX_W = W - 2 * 40


def is_emoji(ch):
    o = ord(ch)
    return o >= 0x1F000 or 0x2600 <= o <= 0x27BF or o in (0x2B50, 0x2B55, 0xFE0F)


_emoji_cache = {}
def emoji_img(ch, size):
    key = (ch, size)
    if key not in _emoji_cache:
        f = ImageFont.truetype(EMOJI, 109)
        im = Image.new('RGBA', (160, 160), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
        im = im.crop(im.getbbox())
        _emoji_cache[key] = im.resize((size, int(size * im.height / im.width)), Image.LANCZOS)
    return _emoji_cache[key]


def runs(line):
    """文字列を [(text, is_emoji)] に分ける（FE0F は捨てる）"""
    out = []
    for ch in line:
        if ord(ch) == 0xFE0F:
            continue
        e = is_emoji(ch)
        if out and out[-1][1] == e and not e:
            out[-1] = (out[-1][0] + ch, False)
        else:
            out.append((ch, e))
    return out


def line_width(line, font):
    w = 0
    for t, e in runs(line):
        w += font.size * 0.95 if e else font.getlength(t)
    return w


def draw_line(im, d, line, font, x, y, fill):
    """y は行の上端（フォントサイズ基準）。絵文字は文字の高さに合わせて描く"""
    for t, e in runs(line):
        if e:
            em = emoji_img(t, int(font.size * 0.9))
            im.alpha_composite(em, (int(x + font.size * 0.02), int(y + font.size * 0.2)))
            x += font.size * 0.95
        else:
            d.text((x, y), t, font=font, fill=fill)
            x += font.getlength(t)


def text_block(im, d, lines, font, lh, cx, top, fill, indent_rest=False):
    """左揃えの行ブロックを、ブロック幅で cx を中心に配置する"""
    ws = [line_width(l, font) + (font.size if indent_rest and i > 0 else 0) for i, l in enumerate(lines)]
    x0 = cx - max(ws) / 2
    for i, l in enumerate(lines):
        dx = font.size if indent_rest and i > 0 else 0
        draw_line(im, d, l, font, x0 + dx, top + i * lh, fill)


# Noto Serif CJK は文字の上に余白があるので、見た目の上端を合わせるための補正
def ink_offset(font):
    return font.getbbox('漢')[1]


def question_font(lines):
    for s in Q_SIZES:
        f = ImageFont.truetype(Q_FONT, s)
        lh = round(s * 1.26)
        if max(line_width(l, f) for l in lines) <= Q_MAX_W and lh * len(lines) <= Q_MAX_H:
            return f, lh
    return None, None


def base_layer(post):
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, BAND_Y - 1], fill=(0, 0, 0, 255))
    d.rectangle([0, BAND_Y + BAND_H, W, H], fill=(0, 0, 0, 255))

    # タイトル（帯の上 60px に下端をそろえる）
    tf = ImageFont.truetype(TITLE_FONT, TITLE_SIZE)
    tlines = ['【必見】'] + post['title'].split('\n')
    top = TITLE_BOTTOM - TITLE_LH * len(tlines) + (TITLE_LH - TITLE_SIZE) - ink_offset(tf) + 4
    text_block(im, d, tlines, tf, TITLE_LH, W / 2, top, 'white')

    # 質問カード
    d.rectangle([CARD_X0, CARD_Y, CARD_X1, HEADER_BOTTOM - 1], fill=(0, 0, 0, 255))
    d.rectangle([CARD_X0, HEADER_BOTTOM, CARD_X1, CARD_BOTTOM], fill=(255, 255, 255, 255))
    hf = ImageFont.truetype(SERIF['Bold'], 27)
    htext = HEADER_TEXT + '💪'
    hw = line_width(htext, hf)
    draw_line(im, d, htext, hf, (CARD_X0 + CARD_X1) / 2 - hw / 2,
              (CARD_Y + HEADER_BOTTOM) / 2 - 27 / 2 - ink_offset(hf) + 1, 'white')
    qlines = post['question'].split('\n')
    qf, qlh = question_font(qlines)
    block_h = qlh * (len(qlines) - 1) + qf.size
    qtop = (HEADER_BOTTOM + CARD_BOTTOM) / 2 - block_h / 2 - ink_offset(qf) / 2
    text_block(im, d, qlines, qf, qlh, (CARD_X0 + CARD_X1) / 2, qtop, (20, 20, 20, 255))
    return im


def answer_layer(post):
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    af = ImageFont.truetype(ANS_FONT, ANS_SIZE)
    alines = post['answer'].split('\n')
    block_h = ANS_LH * (len(alines) - 1) + ANS_SIZE
    top = ANS_CY - block_h / 2 - ink_offset(af) / 2
    text_block(im, d, alines, af, ANS_LH, W / 2, top, 'white', indent_rest=True)
    return im


def cta_layer():
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cf = ImageFont.truetype(CTA_FONT, CTA_SIZE)
    w = line_width(CTA_TEXT, cf)
    draw_line(im, d, CTA_TEXT, cf, W / 2 - w / 2, CTA_CY - CTA_SIZE / 2 - ink_offset(cf) / 2, 'white')
    return im


def check(post):
    """はみ出しチェック。問題があればメッセージのリストを返す"""
    errs = []
    tf = ImageFont.truetype(TITLE_FONT, TITLE_SIZE)
    tl = post['title'].split('\n')
    if len(tl) > 2:
        errs.append(f'title: {len(tl)}行（【必見】の下は2行まで）')
    for l in tl:
        if line_width(l, tf) > TITLE_MAX_W:
            errs.append(f'title「{l}」が長すぎます（1行全角14字程度まで）')
    al = post['answer'].split('\n')
    af = ImageFont.truetype(ANS_FONT, ANS_SIZE)
    if len(al) > 2:
        errs.append(f'answer: {len(al)}行（2行まで）')
    for i, l in enumerate(al):
        if line_width(l, af) + (ANS_SIZE if i else 0) > ANS_MAX_W:
            errs.append(f'answer「{l}」が長すぎます（1行目13字・2行目12字程度まで）')
    ql = post['question'].split('\n')
    if question_font(ql)[0] is None:
        errs.append('question: 行が長すぎるか行数が多すぎます（1行全角12字・8行まで）')
    return errs


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
    return path, random.uniform(0, max(0, dur - DUR - 0.5))


def render(post, broll_dir, out_dir, bgm=None, sfx=None):
    errs = check(post)
    if errs:
        raise SystemExit(f'{post.get("key")}: ' + ' / '.join(errs))
    os.makedirs(out_dir, exist_ok=True)
    tmpd = tempfile.mkdtemp()
    paths = []
    for name, layer in (('base', base_layer(post)), ('ans', answer_layer(post)), ('cta', cta_layer())):
        p = os.path.join(tmpd, name + '.png'); layer.save(p); paths.append(p)
    src, start = pick_broll(post, broll_dir)
    out = os.path.join(out_dir, post['key'] + '.mp4')
    T = f'{DUR:.3f}'
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-ss', f'{start:.2f}', '-t', T, '-i', src]
    for p in paths:
        cmd += ['-loop', '1', '-t', T, '-framerate', str(FPS), '-i', p]
    vf = (f"[0:v]scale={W}:-2,crop={W}:{BAND_H},setsar=1,fps={FPS}[b];"
          f"color=black:s={W}x{H}:d={T}:r={FPS}[bg];"
          f"[bg][b]overlay=0:{BAND_Y}[v1];[v1][1:v]overlay=0:0[v2];"
          f"[v2][2:v]overlay=0:0:enable='lt(t,{ANS_END:.4f})'[v3];"
          f"[v3][3:v]overlay=0:0:enable='gte(t,{CTA_START:.4f})',format=yuv420p[v]")
    # 音：BGM と クリック音を重ねる
    ain, af = [], []
    n = 4
    if bgm:
        ain += ['-i', bgm]
        af.append(f"[{n}:a]atrim=0:{T},asetpts=N/SR/TB,volume=0.9,afade=t=out:st={DUR-0.6:.2f}:d=0.6[m]"); n += 1
    if sfx:
        ain += ['-i', sfx]
        af.append(f"[{n}:a]atrim=0:{T},asetpts=N/SR/TB,volume=0.6[s]"); n += 1
    if bgm and sfx:
        af.append("[m][s]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
    elif bgm:
        af[-1] = af[-1].replace('[m]', '[a]')
    elif sfx:
        af[-1] = af[-1].replace('[s]', '[a]')
    else:
        ain += ['-f', 'lavfi', '-t', T, '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100']
        af.append(f'[{n}:a]anull[a]')
    cmd += ain + ['-filter_complex', vf + ';' + ';'.join(af), '-map', '[v]', '-map', '[a]',
                  '-frames:v', str(FRAMES), '-t', T, '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
                  '-r', str(FPS), '-c:a', 'aac', '-b:a', '160k', '-ar', '44100', '-movflags', '+faststart', out]
    subprocess.run(cmd, check=True)
    for p in paths:
        os.unlink(p)
    os.rmdir(tmpd)
    return out


if __name__ == '__main__':
    args = sys.argv[1:]
    opts = {}
    for k in ('--bgm', '--sfx'):
        if k in args:
            i = args.index(k); opts[k[2:]] = args[i + 1]; del args[i:i + 2]
    posts_path, broll_dir, out_dir = args
    for p in json.load(open(posts_path, encoding='utf-8')):
        print('OK', render(p, broll_dir, out_dir, **opts))
