"""週次ファネル: 表示回数 → 検索クリック → 記事閲覧 → 広告クリック → 確定報酬。

方針
- 全ソースを同じ期間で集計する（metrics.snapshot の period）
- 取れなかった値は None（表では「未取得」）。0 と区別する
- 比率の定義を分ける
    検索CTR        = 検索クリック ÷ 表示回数（Search Console）
    広告クリック率   = affiliate_click イベント数 ÷ 記事の表示回数（GA4・回数ベース）
    利用者クリック率 = 広告をクリックした利用者 ÷ 記事の利用者（GA4・人数ベース）
- 改善候補は、サンプルが基準を満たしたものだけ。最大3件。満たさなければ「保留」
"""
from __future__ import annotations

from .config import ARTICLES_DIR, load_config, parse_front_matter

# 判断に必要な最低サンプル（これ未満は結論を保留）
MIN_IMPRESSIONS = 100
MIN_PAGEVIEWS = 50
MIN_AD_CLICKS = 20


def _titles() -> dict:
    out = {}
    for p in sorted(ARTICLES_DIR.glob("*.md")):
        meta, _ = parse_front_matter(p.read_text(encoding="utf-8"))
        out[p.stem] = {"title": meta.get("title", p.stem), "program_id": meta.get("program_id", "")}
    return out


def _rate(a, b):
    return round(a / b, 4) if (a is not None and b) else None


def build(snap: dict) -> dict:
    g, s, a8 = snap["ga4"], snap["search_console"], snap["a8"]
    ga_ok, sc_ok = g.get("status") == "取得", s.get("status") == "取得"
    rows = []
    for slug, meta in _titles().items():
        p = (g.get("pages") or {}).get(slug, {}) if ga_ok else {}
        ev = [e for e in (g.get("ad_events") or []) if e.get("article") == slug] if ga_ok else []
        sc = (s.get("pages") or {}).get(slug, {}) if sc_ok else {}
        pv = p.get("pageviews", 0) if ga_ok else None
        users = p.get("users", 0) if ga_ok else None
        clicks = sum(e["affiliate_click"] for e in ev) if ga_ok else None
        click_users = sum(e["affiliate_click_users"] for e in ev) if ga_ok else None
        redirects = sum(e["affiliate_redirect"] for e in ev) if ga_ok else None
        imp = sc.get("impressions", 0) if sc_ok else None
        sclicks = sc.get("clicks", 0) if sc_ok else None
        rows.append({
            "slug": slug, "title": meta["title"], "program_id": meta["program_id"],
            "impressions": imp, "search_clicks": sclicks, "search_ctr": _rate(sclicks, imp),
            "pageviews": pv, "users": users, "sources": p.get("sources", {}) if ga_ok else None,
            "ad_clicks": clicks, "ad_click_rate": _rate(clicks, pv),
            "ad_click_users": click_users, "user_click_rate": _rate(click_users, users),
            "redirects": redirects,
            "index": (s.get("index") or {}).get(slug) if sc_ok else None,
            "top_queries": sorted(sc.get("queries", []), key=lambda q: -q["impressions"])[:3] if sc_ok else [],
            "all_queries": sc.get("queries", []) if sc_ok else [],
        })
    ok = a8.get("status") == "取得"
    revenue = a8.get("revenue") if ok else None
    conversions = a8.get("conversions") if ok else None
    pending = (a8.get("pending_conversions"), a8.get("pending_revenue")) if ok else (None, None)
    return {"period": snap["period"], "sources": {k: snap[k]["status"] for k in ("ga4", "search_console", "a8")},
            "rows": rows, "revenue": revenue, "conversions": conversions,
            "pending_conversions": pending[0], "pending_revenue": pending[1]}


def _title_ideas(slug: str) -> list[str]:
    """ChatGPT から受け取ったタイトル案（data/seeds/*.json の title_ideas）。"""
    import json
    ideas = []
    for f in sorted((ARTICLES_DIR.parent.parent / "data" / "seeds").glob("*.json")):
        ideas += json.loads(f.read_text(encoding="utf-8")).get("title_ideas", {}).get(slug, [])
    return ideas


def candidates(f: dict) -> list[dict]:
    """実績から改善候補を出す（優先度順・最大3件）。サンプル不足なら出さない。"""
    out = []
    for r in f["rows"]:
        if r["impressions"] is not None and r["impressions"] >= MIN_IMPRESSIONS and (r["search_ctr"] or 0) < 0.02:
            q = "、".join(x["query"] for x in r["top_queries"]) or "（検索語なし）"
            out.append({"priority": r["impressions"], "slug": r["slug"],
                        "title": f"[改善] 表示されるがクリックされない: {r['title'][:30]}",
                        "body": f"期間 {f['period']['start']}〜{f['period']['end']}：表示 {r['impressions']}回、検索クリック {r['search_clicks']}回"
                                f"（検索CTR {r['search_ctr']:.1%}）。主な検索語：{q}。\n検索語に合わせてタイトル・説明文を見直す。"
                                + ("\nChatGPT のタイトル案（検索語と照らして検証してから使う）：" + " ／ ".join(_title_ideas(r["slug"]))
                                   if _title_ideas(r["slug"]) else "")})
        if r["pageviews"] is not None and r["pageviews"] >= MIN_PAGEVIEWS and (r["ad_click_rate"] or 0) < 0.01:
            out.append({"priority": r["pageviews"], "slug": r["slug"],
                        "title": f"[改善] 読まれるが広告がクリックされない: {r['title'][:30]}",
                        "body": f"期間 {f['period']['start']}〜{f['period']['end']}：記事の表示 {r['pageviews']}回、広告クリック {r['ad_clicks']}回"
                                f"（表示あたり {(r['ad_click_rate'] or 0):.1%}・利用者ベース {(r['user_click_rate'] or 0):.1%}）。\n"
                                "読者の疑問に合った位置に、確認できる内容を具体的に書いた広告ボタンがあるかを見直す（報酬の高さで案件を変えない）。"})
        if (r["ad_clicks"] or 0) >= MIN_AD_CLICKS and f["conversions"] == 0:
            out.append({"priority": r["ad_clicks"], "slug": r["slug"],
                        "title": f"[改善] 広告はクリックされるが成果がない: {r['title'][:30]}",
                        "body": f"広告クリック {r['ad_clicks']}回、A8の成果 0件（同期間）。案件と読者の悩みのずれ、記事で伝えている条件と公式ページの差を確認する。"})
    out.sort(key=lambda c: -c["priority"])
    return out[:3]


def _fmt(v, pct=False):
    if v is None:
        return "未取得"
    return f"{v:.1%}" if pct else f"{v:,}"


def markdown(f: dict, cands: list[dict]) -> str:
    p = f["period"]
    lines = [f"## ファネル（{p['start']}〜{p['end']}、全ソース同一期間）", "",
             "取得状況：" + " ／ ".join(f"{k}：{v}" for k, v in f["sources"].items()), "",
             "| 記事 | 検索表示 | 検索クリック | 検索CTR | 記事表示 | 利用者 | 広告クリック | 表示あたり | 利用者ベース | インデックス |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in f["rows"]:
        lines.append(f"| {r['title'][:24]} | {_fmt(r['impressions'])} | {_fmt(r['search_clicks'])} | {_fmt(r['search_ctr'], True)} | "
                     f"{_fmt(r['pageviews'])} | {_fmt(r['users'])} | {_fmt(r['ad_clicks'])} | {_fmt(r['ad_click_rate'], True)} | "
                     f"{_fmt(r['user_click_rate'], True)} | {r['index'] or '未取得'} |")
    # 案件ごとの記事PV（総PVではなく、その案件の広告を載せた記事のPVだけを合計）
    progs: dict[str, dict] = {}
    for r in f["rows"]:
        g = progs.setdefault(r["program_id"] or "（なし）", {"articles": 0, "pageviews": None, "ad_clicks": None})
        g["articles"] += 1
        for k in ("pageviews", "ad_clicks"):
            if r[k] is not None:
                g[k] = (g[k] or 0) + r[k]
    lines += ["", "### 案件ごと（その案件の広告を載せた記事だけを集計）", "",
              "| 案件 | 記事数 | 記事表示 | 広告クリック | 表示あたり |", "|---|---|---|---|---|"]
    for pid, g in progs.items():
        lines.append(f"| {pid} | {g['articles']} | {_fmt(g['pageviews'])} | {_fmt(g['ad_clicks'])} | "
                     f"{_fmt(_rate(g['ad_clicks'], g['pageviews']), True)} |")
    srcs: dict[str, int] = {}
    for r in f["rows"]:
        for ch, v in (r.get("sources") or {}).items():
            srcs[ch] = srcs.get(ch, 0) + v
    lines += ["", "### 記事表示の流入元（GA4の既定チャネル）", "",
              ("、".join(f"{ch} {v}回" for ch, v in sorted(srcs.items(), key=lambda x: -x[1])) or
               ("データなし" if f["sources"]["ga4"] == "取得" else "未取得"))]
    # 観測中の検索語（data/watch_queries.json）。少ないうちは記事を変えず、推移だけを見る
    import json as _json
    wpath = ARTICLES_DIR.parent.parent / "data" / "watch_queries.json"
    if wpath.exists():
        watch = _json.loads(wpath.read_text(encoding="utf-8")).get("queries", [])
        if watch:
            lines += ["", "### 観測中の検索語（記事は変えず、推移だけを見る）", "",
                      "| 検索語 | 記事 | 初めて見た日 | 今期の表示 | 今期のクリック | 平均順位 |", "|---|---|---|---|---|---|"]
            for w in watch:
                hit = [q for r in f["rows"] if r["slug"] == w["article"] for q in r.get("all_queries", []) if q["query"] == w["query"]]
                sc_ok = f["sources"]["search_console"] == "取得"
                imp = sum(q["impressions"] for q in hit) if sc_ok else None
                clk = sum(q["clicks"] for q in hit) if sc_ok else None
                pos = hit[0]["position"] if hit else "—"
                lines.append(f"| {w['query']} | {w['article'][:20]} | {w['first_seen']} | {_fmt(imp)} | {_fmt(clk)} | {pos} |")
    lines += ["", f"確定報酬（A8）：{_fmt(f['revenue'])}{'円' if f['revenue'] is not None else ''}（{_fmt(f['conversions'])}件）"
              f" ／ 承認待ち（発生）：{_fmt(f.get('pending_revenue'))}{'円' if f.get('pending_revenue') is not None else ''}"
              f"（{_fmt(f.get('pending_conversions'))}件） ※収益の評価は確定のみ。入金は別管理", "",
              "- 広告クリック＝記事内ボタンの affiliate_click イベント。中継ページ到達（affiliate_redirect）は別集計で、合算しない",
              "- 利用者数は記事ごとの合計のため、複数記事を読んだ人は重複して数えられる", "",
              "## 改善候補（実績にもとづく・最大3件）", ""]
    if cands:
        lines += [f"{i}. **{c['title']}** — {c['body']}" for i, c in enumerate(cands, 1)]
    else:
        lines.append(f"データが判断基準（検索表示{MIN_IMPRESSIONS}回・記事表示{MIN_PAGEVIEWS}回・広告クリック{MIN_AD_CLICKS}回）に届いていないため、結論を保留して観測を続けます。")
    return "\n".join(lines) + "\n"
