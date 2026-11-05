#!/usr/bin/env python3
"""
毎晩の自動処理：翌日分の投稿JSONから動画を作り、GitHub Pages 用リポジトリに配置する。
  python3 build_day.py posts_YYYY-MM-DD.json REPO_DIR
posts の各要素: key, datetime("YYYY/MM/DD HH:MM"), account(保護者/受験生), title, question, answer, caption
出力:
  REPO_DIR/videos/<key>.mp4
  REPO_DIR/queue/<YYYY-MM-DD>.json   ← GASの importQueue が読む
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_qa import render

src, repo = sys.argv[1], sys.argv[2]
posts = json.load(open(src, encoding='utf-8'))
broll = os.path.join(repo, 'assets', 'broll')
bgm_dir = os.path.join(repo, 'assets', 'bgm')
bgms = sorted(os.path.join(bgm_dir, f) for f in os.listdir(bgm_dir)) if os.path.isdir(bgm_dir) else []

out = []
for i, p in enumerate(posts):
    for k in ('key', 'datetime', 'account', 'title', 'question', 'answer', 'caption'):
        if not p.get(k):
            raise SystemExit(f'{p.get("key")}: {k} が空です')
    if len(p['caption']) > 2200:
        raise SystemExit(f'{p["key"]}: キャプションが2200字を超えています')
    bgm = bgms[i % len(bgms)] if bgms else None
    render(p, broll, os.path.join(repo, 'videos'), bgm)
    out.append({**p, 'video': f'videos/{p["key"]}.mp4'})

day = posts[0]['datetime'][:10].replace('/', '-')
os.makedirs(os.path.join(repo, 'queue'), exist_ok=True)
with open(os.path.join(repo, 'queue', f'{day}.json'), 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(f'posts={len(out)} day={day}')
