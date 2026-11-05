#!/usr/bin/env python3
"""
毎晩の自動処理：翌日分の投稿JSONから動画を作り、GitHub Pages 用リポジトリに配置する。
  python3 build_day.py posts_YYYY-MM-DD.json REPO_DIR BGM_DIR
posts の各要素: key, datetime("YYYY/MM/DD HH:MM"), account(保護者/受験生), title, question, answer, caption
BGM_DIR: サビ8秒を切り出した音源（非公開のGoogleドライブから取得。規約上、公開リポジトリには置かない）
  保護者 → 毎回 In-Between.m4a（同じ音源で統一）
  受験生 → 残りの曲を日付と投稿順で日替わり
出力:
  REPO_DIR/videos/<key>.mp4
  REPO_DIR/queue/<YYYY-MM-DD>.json   ← GASの importQueue が読む
"""
import json, os, sys
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_qa import render

PARENT_BGM = 'In-Between.m4a'

src, repo, bgm_dir = sys.argv[1], sys.argv[2], sys.argv[3]
posts = json.load(open(src, encoding='utf-8'))
broll = os.path.join(repo, 'assets', 'broll')
student_bgms = sorted(f for f in os.listdir(bgm_dir) if f.endswith('.m4a') and f != PARENT_BGM)
if not os.path.exists(os.path.join(bgm_dir, PARENT_BGM)) or not student_bgms:
    raise SystemExit('BGMが揃っていません: ' + bgm_dir)

out, s_count = [], 0
for p in posts:
    for k in ('key', 'datetime', 'account', 'title', 'question', 'answer', 'caption'):
        if not p.get(k):
            raise SystemExit(f'{p.get("key")}: {k} が空です')
    if p['account'] not in ('保護者', '受験生'):
        raise SystemExit(f'{p["key"]}: account は 保護者 か 受験生')
    if len(p['caption']) > 2200:
        raise SystemExit(f'{p["key"]}: キャプションが2200字を超えています')
    if p['account'] == '保護者':
        bgm = PARENT_BGM
    else:
        y, m, d = map(int, p['datetime'][:10].split('/'))
        bgm = student_bgms[(date(y, m, d).toordinal() * 2 + s_count) % len(student_bgms)]
        s_count += 1
    render(p, broll, os.path.join(repo, 'videos'), os.path.join(bgm_dir, bgm))
    out.append({**p, 'video': f'videos/{p["key"]}.mp4', 'bgm': bgm.replace('.m4a', '')})

day = posts[0]['datetime'][:10].replace('/', '-')
os.makedirs(os.path.join(repo, 'queue'), exist_ok=True)
with open(os.path.join(repo, 'queue', f'{day}.json'), 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(f'posts={len(out)} day={day}')
