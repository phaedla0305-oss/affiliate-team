"""計測データの取得（Claude API を使わない）。

- GA4 Data API: 記事別の閲覧数・利用者数、広告クリック（affiliate_click）と中継ページ到達（affiliate_redirect）
- Search Console API: 記事別の表示回数・クリック数・検索語、サイトマップ、インデックス状況
取れたもの・取れなかったものを区別して返す（取れなければ値を作らず status に理由を書く）。

必要な環境変数:
  GOOGLE_APPLICATION_CREDENTIALS … サービスアカウント鍵（閲覧権限のみ）
  GA4_PROPERTY_ID               … GA4 のプロパティID
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.parse

from .config import REPORTS_DIR, load_config, write_json, write_text

SLUG_RE = re.compile(r"/articles/([a-z0-9-]+)\.html")
GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"


def _slug(path: str) -> str | None:
    m = SLUG_RE.search(path or "")
    return m.group(1) if m else None


def _period(days: int, include_today: bool = False) -> tuple[str, str]:
    end = dt.date.today() - dt.timedelta(days=0 if include_today else 1)
    return (end - dt.timedelta(days=days - 1)).isoformat(), end.isoformat()


# ---------------- GA4 ----------------
def ga4(start: str, end: str) -> dict:
    prop = os.getenv("GA4_PROPERTY_ID") or str(load_config()["site"].get("ga4_property_id") or "")
    if not prop or not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return {"status": "未取得（GA4の認証情報が未設定）"}
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (DateRange, Dimension, Filter, FilterExpression,
                                                        Metric, RunReportRequest)
        client = BetaAnalyticsDataClient()

        def run(dims, metrics, event=None):
            req = RunReportRequest(property=f"properties/{prop}", dimensions=[Dimension(name=d) for d in dims],
                                   metrics=[Metric(name=m) for m in metrics],
                                   date_ranges=[DateRange(start_date=start, end_date=end)], limit=10000)
            if event:
                req.dimension_filter = FilterExpression(filter=Filter(
                    field_name="eventName", string_filter=Filter.StringFilter(value=event)))
            return [([v.value for v in r.dimension_values], [float(v.value or 0) for v in r.metric_values])
                    for r in client.run_report(req).rows]

        pages, other_paths = {}, {}
        for (path,), (pv, users) in run(["pagePath"], ["screenPageViews", "totalUsers"]):
            s = _slug(path)
            if s and "/zaitaku-toolbox/" in path:
                p = pages.setdefault(s, {"pageviews": 0, "users": 0})
                p["pageviews"] += int(pv)
                p["users"] += int(users)  # パスごとの利用者数の合計（同じ人が複数パスにいると重複しうる）
            else:
                other_paths[path] = int(pv)  # トップ・旧URL・中継ページなど
        # 流入元（GA4 の既定チャネル：Organic Search／Direct／Organic Social など）を記事ごとに
        for (path, ch), (pv,) in run(["pagePath", "sessionDefaultChannelGroup"], ["screenPageViews"]):
            s = _slug(path)
            if s and "/zaitaku-toolbox/" in path and s in pages:
                src = pages[s].setdefault("sources", {})
                src[ch] = src.get(ch, 0) + int(pv)
        clicks = {}
        for event in ("affiliate_click", "affiliate_redirect"):
            for (article, pid), (cnt, users) in run(["customEvent:article", "customEvent:program_id"],
                                                    ["eventCount", "totalUsers"], event=event):
                c = clicks.setdefault(f"{article}|{pid}", {"article": article, "program_id": pid,
                                                             "affiliate_click": 0, "affiliate_click_users": 0,
                                                             "affiliate_redirect": 0})
                c[event] += int(cnt)
                if event == "affiliate_click":
                    c["affiliate_click_users"] += int(users)
        return {"status": "取得", "pages": pages, "other_paths": other_paths, "ad_events": list(clicks.values())}
    except Exception as e:  # 権限・API無効などはそのまま理由を返す
        return {"status": f"未取得（{type(e).__name__}: {str(e)[:200]}）"}


# ---------------- Search Console ----------------
def gsc(start: str, end: str) -> dict:
    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not path:
        return {"status": "未取得（認証情報が未設定）"}
    site = load_config()["site"]["url"].rstrip("/") + "/"
    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
        sess = AuthorizedSession(service_account.Credentials.from_service_account_file(path, scopes=[GSC_SCOPE]))
        enc = urllib.parse.quote(site, safe="")
        base = f"https://searchconsole.googleapis.com/webmasters/v3/sites/{enc}"
        r = sess.post(f"{base}/searchAnalytics/query",
                      json={"startDate": start, "endDate": end, "dimensions": ["page", "query"], "rowLimit": 1000})
        if r.status_code != 200:
            return {"status": f"未取得（Search Console API {r.status_code}: {r.text[:200]}）"}
        pages: dict[str, dict] = {}
        for row in r.json().get("rows", []):
            page, query = row["keys"]
            s = _slug(page) or page
            p = pages.setdefault(s, {"impressions": 0, "clicks": 0, "queries": []})
            p["impressions"] += int(row.get("impressions", 0))
            p["clicks"] += int(row.get("clicks", 0))
            p["queries"].append({"query": query, "impressions": int(row.get("impressions", 0)),
                                 "clicks": int(row.get("clicks", 0)), "position": round(row.get("position", 0), 1)})
        sm = sess.get(f"{base}/sitemaps")
        sitemaps = [{"path": s.get("path"), "lastDownloaded": s.get("lastDownloaded"), "errors": s.get("errors"),
                     "warnings": s.get("warnings"), "isPending": s.get("isPending")}
                    for s in (sm.json().get("sitemap", []) if sm.status_code == 200 else [])]
        index = {}
        for url in _article_urls(site):
            ir = sess.post("https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
                           json={"inspectionUrl": url, "siteUrl": site})
            res = ir.json().get("inspectionResult", {}).get("indexStatusResult", {}) if ir.status_code == 200 else {}
            index[_slug(url) or url] = res.get("coverageState") or f"取得失敗 {ir.status_code}"
        return {"status": "取得", "pages": pages, "sitemaps": sitemaps, "index": index}
    except Exception as e:
        return {"status": f"未取得（{type(e).__name__}: {str(e)[:200]}）"}


def _article_urls(site: str) -> list[str]:
    from .config import ARTICLES_DIR
    return [f"{site}articles/{p.stem}.html" for p in sorted(ARTICLES_DIR.glob("*.md"))]


# ---------------- A8（CSV） ----------------
def a8(start: str, end: str) -> dict:
    """A8 の成果。status 列（発生／確定／否認／入金）で分けて集計する。
    status 列がない古い形式は「確定」とみなす。期間は成果の発生日（date）で区切る。"""
    from .measure import _num, _read
    rows = [r for r in _read("asp") if start <= r.get("date", "") <= end]
    if not rows:
        return {"status": "未取得（A8の成果CSVがない）"}
    by = {}
    for r in rows:
        st = (r.get("status") or "確定").strip()
        b = by.setdefault(st, {"conversions": 0, "revenue": 0})
        b["conversions"] += int(_num(r.get("conversions")))
        b["revenue"] += int(_num(r.get("revenue")))
    conf = by.get("確定", {"conversions": 0, "revenue": 0})
    return {"status": "取得", "by_status": by,
            "conversions": conf["conversions"], "revenue": conf["revenue"],  # 収益の評価は確定のみ
            "pending_conversions": by.get("発生", {}).get("conversions", 0),
            "pending_revenue": by.get("発生", {}).get("revenue", 0)}


def snapshot(days: int = 28, include_today: bool = False) -> dict:
    start, end = _period(days, include_today)
    return {"period": {"start": start, "end": end, "note": "両端を含む。GA4・Search Console・A8 で同じ期間"},
            "ga4": ga4(start, end), "search_console": gsc(start, end), "a8": a8(start, end)}


def run(days: int = 28, include_today: bool = False) -> dict:
    snap = snapshot(days, include_today)
    write_json(REPORTS_DIR / "metrics_snapshot.json", snap)
    print(json.dumps({k: (v if k == "period" else {"status": v.get("status")}) for k, v in snap.items()},
                     ensure_ascii=False))
    print(json.dumps(snap, ensure_ascii=False)[:6000])
    return snap
