"""⑤ 販売（集客）: 公開済み記事の SNS 告知。

既定は「投稿キュー（reports/sns_queue.md）を作るだけ」。
config.yaml の sns.live: true か環境変数 SNS_LIVE=1、かつ X API の鍵があるときだけ実投稿する。
A/B テストのため、投稿ごとに案を順番に使い、UTM で案番号を記録する。
"""
from __future__ import annotations

import json
import os

from .config import ROOT, REPORTS_DIR, SNS_DIR, is_dry_run, load_config, today, write_json, write_text

STATE = ROOT / "data" / "sns_posted.json"


def _post_x(text: str) -> str:
    import tweepy  # pip install tweepy（実投稿するときだけ必要）

    client = tweepy.Client(
        consumer_key=os.environ["X_API_KEY"], consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"], access_token_secret=os.environ["X_ACCESS_SECRET"],
    )
    return str(client.create_tweet(text=text).data["id"])




def _jst_today() -> str:
    import datetime as _d
    return (_d.datetime.now(_d.timezone.utc) + _d.timedelta(hours=9)).date().isoformat()


def run(max_posts: int = 1) -> int:
    """1日（日本時間）に最大 max_posts 件だけ投稿する。公開のたびに呼ばれても、その日に投稿済みなら投稿しない。
    投稿する記事は「投稿回数が少ない記事 → 新しい記事」の順に選び、同じ記事を続けて投稿しない。"""
    cfg = load_config()
    live = (cfg["sns"].get("live") or os.getenv("SNS_LIVE") == "1") and not is_dry_run()
    keys = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")
    if live and not all(os.getenv(k) for k in keys):
        print("[販売] X の API キーが未登録のため、投稿キューの作成に切り替えます")
        live = False
    raw = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    state = raw if "posts" in raw else {"posts": raw, "last_post_date": None, "posted_today": 0}  # 旧形式から移行
    day = _jst_today()
    if state.get("last_post_date") != day:
        state["posted_today"] = 0
    base = cfg["site"]["url"].rstrip("/")

    items = []
    for f in SNS_DIR.glob("*.json"):
        sns = json.loads(f.read_text(encoding="utf-8"))
        slug, posts = sns["slug"], sns.get("x_posts", [])
        n = state["posts"].get(slug, 0)
        if n < len(posts):
            items.append({"n": n, "created": str(sns.get("created", "")), "slug": slug, "posts": posts})
    items.sort(key=lambda x: x["created"], reverse=True)  # 新しい記事を先に
    items.sort(key=lambda x: x["n"])                      # 投稿回数が少ない記事を優先（安定ソート）

    queue, posted = [], 0
    for it in items:
        n, slug = it["n"], it["slug"]
        url = f"{base}/articles/{slug}.html?utm_source=x&utm_medium=social&utm_campaign={slug}&utm_content=v{n + 1}"
        text = it["posts"][n] + "\n" + url
        if live and state["posted_today"] < max_posts:
            pid = _post_x(text)
            print(f"[販売] X に投稿: {slug} v{n + 1} (id={pid})")
            state["posts"][slug] = n + 1
            state["posted_today"] += 1
            state["last_post_date"] = day
            posted += 1
        else:
            queue.append(f"## {slug}（案 v{n + 1}）\n\n```\n{text}\n```\n")
    if live and not posted and state["posted_today"] >= max_posts:
        print(f"[販売] 本日（{day}）は投稿済みのため、追加の投稿はしません")

    write_json(STATE, state)
    if queue:
        header = f"# SNS 投稿キュー（{today()}）\n\n手動投稿する場合はコピーして使ってください。\n\n"
        write_text(REPORTS_DIR / "sns_queue.md", header + "\n".join(queue))
        print(f"[販売] 投稿キュー {len(queue)} 件: reports/sns_queue.md")
    return posted
