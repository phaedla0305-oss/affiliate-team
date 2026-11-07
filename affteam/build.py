"""④ 実装: Markdown 記事から静的サイト（GitHub Pages 用）を生成する。

- 全ページの冒頭に PR 表記を自動挿入（ステマ規制対応）
- [[aff:案件ID|文言]] → /go/案件ID.html 経由のリンク（rel="sponsored"、クリック計測付き）
- テンプレートやデザインの改善は Copilot coding agent に Issue で任せる想定
"""
from __future__ import annotations

import html
import json
import re
import shutil

import markdown

from .config import ARTICLES_DIR, ROOT, SITE_DIR, load_config, parse_front_matter, write_text

CSS = """
:root{--bg:#fff;--fg:#1d1d1f;--muted:#6e6e73;--accent:#0a66c2;--pr:#fff4e5;--line:#e5e5ea}
@media (prefers-color-scheme:dark){:root{--bg:#121214;--fg:#f2f2f7;--muted:#a1a1a6;--accent:#4ea1ff;--pr:#3a2a12;--line:#2c2c2e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.85 system-ui,"Hiragino Sans","Noto Sans JP",sans-serif}
main,header,footer{max-width:760px;margin:0 auto;padding:0 16px}header{padding-top:24px}header a{color:var(--fg);text-decoration:none;font-weight:700}
.pr{background:var(--pr);border-radius:8px;padding:8px 12px;font-size:13px;margin:16px 0}
h1{font-size:1.6rem;line-height:1.4}h2{margin-top:2.2em;padding-bottom:.3em;border-bottom:1px solid var(--line)}
a{color:var(--accent)}.cta{display:inline-block;background:var(--accent);color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:700;margin:8px 0}
.meta{color:var(--muted);font-size:14px}ul.list{padding:0;list-style:none}ul.list li{padding:12px 0;border-bottom:1px solid var(--line)}
footer{color:var(--muted);font-size:13px;padding:40px 16px}
"""


def _ga(ga4_id: str) -> str:
    if not ga4_id:
        return "<script>window.gtag=function(){};</script>"
    return (f'<script async src="https://www.googletagmanager.com/gtag/js?id={ga4_id}"></script>'
            f"<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}"
            f"gtag('js',new Date());gtag('config','{ga4_id}');</script>")


def _page(cfg: dict, title: str, desc: str, body: str, prefix: str) -> str:
    s = cfg["site"]
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><meta name="description" content="{html.escape(desc)}">
<link rel="stylesheet" href="{prefix}style.css">{_ga(s.get('ga4_id', ''))}</head><body>
<header><a href="{prefix}index.html">{html.escape(s['name'])}</a></header>
<main><p class="pr">{html.escape(cfg['compliance']['pr_label'])}</p>{body}</main>
<footer>© {html.escape(s['name'])} ／ 当サイトはアフィリエイトプログラムに参加しています。 ／ <a href="{prefix}privacy.html">プライバシーポリシー</a></footer></body></html>"""


def _aff_links(body_md: str, slug: str) -> str:
    def repl(m: re.Match) -> str:
        pid, label = m.group(1), (m.group(2) or "公式サイトを見る")
        return (f'<a class="cta" href="../go/{pid}.html?from={slug}" rel="sponsored noopener" '
                f"onclick=\"gtag('event','affiliate_click',{{program_id:'{pid}',article:'{slug}',transport_type:'beacon'}})\">{html.escape(label)}</a>")
    return re.sub(r"\[\[aff:([a-zA-Z0-9_-]+)(?:\|([^\]]+))?\]\]", repl, body_md)


def run() -> int:
    cfg = load_config()
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    write_text(SITE_DIR / "style.css", CSS)
    write_text(SITE_DIR / ".nojekyll", "")

    index = []
    for path in sorted(ARTICLES_DIR.glob("*.md")):
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        slug = str(meta.get("slug") or path.stem)
        body_html = markdown.markdown(_aff_links(body, slug), extensions=["tables", "fenced_code"])
        page = (f"<h1>{html.escape(meta.get('title', slug))}</h1>"
                f"<p class=\"meta\">{meta.get('date', '')} ／ {html.escape(cfg['site'].get('author', ''))}</p>{body_html}")
        write_text(SITE_DIR / "articles" / f"{slug}.html", _page(cfg, meta.get("title", slug), meta.get("description", ""), page, "../"))
        index.append((str(meta.get("date", "")), slug, meta.get("title", slug), meta.get("description", "")))

    # 広告リンクの中継ページ（クリック計測 → 広告URLへ移動）
    for p in cfg["programs"]:
        url = json.dumps(p["url"])
        body = (f"<p>{html.escape(p['name'])} の公式サイトへ移動します…</p>"
                f"<p><a href=\"{html.escape(p['url'])}\" rel=\"sponsored noopener\">移動しない場合はこちら</a></p>"
                f"<script>var a=new URLSearchParams(location.search).get('from')||'direct',d=false;"
                f"function go(){{if(!d){{d=true;location.replace({url})}}}}"
                f"gtag('event','affiliate_redirect',{{program_id:'{p['id']}',article:a,transport_type:'beacon',event_callback:go}});"
                f"setTimeout(go,1200);</script>")
        write_text(SITE_DIR / "go" / f"{p['id']}.html",
                   _page(cfg, p["name"], "", body, "../").replace("<head>", '<head><meta name="robots" content="noindex">'))

    name = html.escape(cfg["site"]["name"])
    privacy = f"""<h1>プライバシーポリシー</h1>
<h2>アクセス解析ツールについて</h2>
<p>{name}（以下「当サイト」）は、Googleによるアクセス解析ツール「Googleアナリティクス」を利用しています。Googleアナリティクスはデータの収集のためにCookieを使用します。このデータは匿名で収集されており、個人を特定するものではありません。</p>
<p>この機能はブラウザの設定でCookieを無効にすることで、収集を拒否できます。詳しくは<a href="https://marketingplatform.google.com/about/analytics/terms/jp/" rel="noopener">Googleアナリティクス利用規約</a>および<a href="https://policies.google.com/technologies/partner-sites?hl=ja" rel="noopener">Googleのポリシーと規約</a>をご覧ください。</p>
<h2>広告について</h2>
<p>当サイトは、A8.netなどのアフィリエイトプログラムに参加しています。記事内のリンクから商品・サービスを申し込むと、当サイトが広告主から報酬を受け取る場合があります。広告リンクを経由した場合、ASP・広告主がCookie等を用いて成果を計測することがあります。</p>
<p>記事の内容は、公式情報などをもとに当サイトが独自に作成しています。</p>
<h2>免責事項</h2>
<p>掲載情報は記事公開時点のものです。料金・仕様などの最新情報は、各サービスの公式サイトでご確認ください。</p>"""
    write_text(SITE_DIR / "privacy.html", _page(cfg, f"プライバシーポリシー｜{cfg['site']['name']}", "", privacy, ""))

    items = "".join(f'<li><a href="articles/{s}.html">{html.escape(t)}</a><div class="meta">{d} {html.escape(desc)}</div></li>'
                    for d, s, t, desc in sorted(index, reverse=True))
    write_text(SITE_DIR / "index.html", _page(cfg, cfg["site"]["name"], cfg["niche"], f"<h1>新着記事</h1><ul class=\"list\">{items}</ul>", ""))
    base = cfg["site"]["url"].rstrip("/")
    urls = "".join(f"<url><loc>{base}/articles/{s}.html</loc><lastmod>{d}</lastmod></url>" for d, s, _, _ in index)
    write_text(SITE_DIR / "sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
    print(f"[実装] サイト生成: 記事 {len(index)} 本 → {SITE_DIR.relative_to(ROOT)}/")
    return len(index)
