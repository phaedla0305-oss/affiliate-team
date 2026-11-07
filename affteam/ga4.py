"""GA4 Data API から直近7日間の記事別データを取得し、data/metrics/ga/ に CSV で保存する。

必要なもの（どちらも GitHub Actions で設定）:
  - 環境変数 GA4_PROPERTY_ID（config.yaml の site.ga4_property_id でも可）
  - 環境変数 GOOGLE_APPLICATION_CREDENTIALS（サービスアカウント鍵 JSON のパス。閲覧者権限のみ）
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
from collections import defaultdict

from .config import METRICS_DIR, load_config

SLUG_RE = re.compile(r"/articles/([a-z0-9-]+)\.html")


def _client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient

    return BetaAnalyticsDataClient()


def _report(client, prop: str, dims: list[str], metric: str, event: str | None = None):
    from google.analytics.data_v1beta.types import DateRange, Dimension, Filter, FilterExpression, Metric, RunReportRequest

    req = RunReportRequest(
        property=f"properties/{prop}",
        dimensions=[Dimension(name=d) for d in dims],
        metrics=[Metric(name=metric)],
        date_ranges=[DateRange(start_date="7daysAgo", end_date="yesterday")],
        limit=10000,
    )
    if event:
        req.dimension_filter = FilterExpression(filter=Filter(field_name="eventName", string_filter=Filter.StringFilter(value=event)))
    return [([v.value for v in r.dimension_values], float(r.metric_values[0].value or 0)) for r in client.run_report(req).rows]


def fetch() -> str | None:
    prop = os.getenv("GA4_PROPERTY_ID") or str(load_config()["site"].get("ga4_property_id") or "")
    if not prop or not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        print("[効果測定] GA4 の自動取得は未設定（data/metrics/ga/ の CSV を使います）")
        return None
    client = _client()
    rows: dict[tuple[str, str], dict] = defaultdict(lambda: {"pageviews": 0, "affiliate_clicks": 0})

    for (date, path), v in _report(client, prop, ["date", "pagePath"], "screenPageViews"):
        m = SLUG_RE.search(path)
        if m:
            rows[(date, m.group(1))]["pageviews"] += int(v)
    for (date, article), v in _report(client, prop, ["date", "customEvent:article"], "eventCount", event="affiliate_click"):
        if article and article != "(not set)":
            rows[(date, article)]["affiliate_clicks"] += int(v)

    end = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    out = METRICS_DIR / "ga" / f"ga4_{end}.csv"  # 同じ日に再実行しても上書きされ、二重集計しない
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["date", "slug", "pageviews", "affiliate_clicks"])
        for (date, slug), v in sorted(rows.items()):
            w.writerow([f"{date[:4]}-{date[4:6]}-{date[6:]}", slug, v["pageviews"], v["affiliate_clicks"]])
    print(f"[効果測定] GA4 から {len(rows)} 行を取得: {out.relative_to(METRICS_DIR.parent.parent)}")
    return str(out)
