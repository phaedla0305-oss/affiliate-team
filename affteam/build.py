"""④ 実装: Markdown 記事から静的サイト（GitHub Pages 用）を生成する。

- 全ページの冒頭に PR 表記を自動挿入（ステマ規制対応）
- [[aff:案件ID|文言]] → /go/案件ID.html 経由のリンク（rel="sponsored"、クリック計測付き）
- SEO: canonical / OGP / 構造化データ（Article・Breadcrumb）/ 目次 / 関連記事 / sitemap.xml
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
:root{--bg:#fff;--fg:#1d1d1f;--muted:#6e6e73;--accent:#0a66c2;--pr:#fff4e5;--line:#e5e5ea;--box:#f5f5f7}
@media (prefers-color-scheme:dark){:root{--bg:#121214;--fg:#f2f2f7;--muted:#a1a1a6;--accent:#4ea1ff;--pr:#3a2a12;--line:#2c2c2e;--box:#1c1c1e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.85 system-ui,"Hiragino Sans","Noto Sans JP",sans-serif}
main,header,footer{max-width:760px;margin:0 auto;padding:0 16px}header{padding-top:24px}header a{color:var(--fg);text-decoration:none;font-weight:700}
.pr{background:var(--pr);border-radius:8px;padding:8px 12px;font-size:13px;margin:16px 0}
h1{font-size:1.6rem;line-height:1.4}h2{margin-top:2.2em;padding-bottom:.3em;border-bottom:1px solid var(--line)}
a{color:var(--accent)}.cta{display:inline-block;background:var(--accent);color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:700;margin:8px 0}
.meta{color:var(--muted);font-size:14px}ul.list{padding:0;list-style:none}ul.list li{padding:12px 0;border-bottom:1px solid var(--line)}
table{border-collapse:collapse;width:100%;display:block;overflow-x:auto}th,td{border:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}
.toc,.related{background:var(--box);border-radius:10px;padding:12px 18px;margin:24px 0}.toc ul{margin:0;padding-left:1.2em}.toc>p,.related>p{margin:0 0 4px;font-weight:700}
pre{background:var(--box);border-radius:8px;padding:12px;overflow-x:auto;font-size:13px;line-height:1.6;white-space:pre}code{font-family:ui-monospace,"Cascadia Mono",Consolas,monospace}img{max-width:100%;height:auto}
.next{border-left:4px solid var(--accent);padding:4px 0 4px 12px;margin:20px 0}
footer{color:var(--muted);font-size:13px;padding:40px 16px}
"""


def _ga(ga4_id: str) -> str:
    if not ga4_id:
        return "<script>window.gtag=function(){};</script>"
    # ?notrack=1 で開いた端末は以後計測しない（運営者・動作確認のアクセスを除外。?notrack=0 で解除）
    return ("<script>(function(){var q=new URLSearchParams(location.search).get('notrack');"
            "try{if(q==='1')localStorage.setItem('zt_notrack','1');if(q==='0')localStorage.removeItem('zt_notrack');"
            "window.ztNoTrack=localStorage.getItem('zt_notrack')==='1'}catch(e){window.ztNoTrack=false}})();"
            "window.dataLayer=window.dataLayer||[];window.gtag=function(){if(!window.ztNoTrack)dataLayer.push(arguments)};"
            f"if(!window.ztNoTrack){{var s=document.createElement('script');s.async=1;"
            f"s.src='https://www.googletagmanager.com/gtag/js?id={ga4_id}';document.head.appendChild(s);"
            f"gtag('js',new Date());gtag('config','{ga4_id}')}}</script>")


def _page(cfg: dict, title: str, desc: str, body: str, prefix: str, *, path: str = "",
          og_type: str = "website", jsonld: list | None = None, noindex: bool = False) -> str:
    s = cfg["site"]
    base = s["url"].rstrip("/")
    url = f"{base}/{path}" if path else f"{base}/"
    head = [
        '<meta charset="utf-8">', '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>{html.escape(title)}</title>", f'<meta name="description" content="{html.escape(desc)}">',
        f'<link rel="canonical" href="{url}">',
        f'<meta property="og:title" content="{html.escape(title)}">', f'<meta property="og:description" content="{html.escape(desc)}">',
        f'<meta property="og:type" content="{og_type}">', f'<meta property="og:url" content="{url}">',
        f'<meta property="og:site_name" content="{html.escape(s["name"])}">', '<meta property="og:locale" content="ja_JP">',
        '<meta name="twitter:card" content="summary">',
        f'<link rel="stylesheet" href="{prefix}style.css">',
    ]
    if noindex:
        head.append('<meta name="robots" content="noindex">')
    if s.get("gsc_verification"):
        head.append(f'<meta name="google-site-verification" content="{html.escape(s["gsc_verification"])}">')
    for ld in jsonld or []:
        head.append(f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>')
    head.append(_ga(s.get("ga4_id", "")))
    return f"""<!doctype html><html lang="ja"><head>{''.join(head)}</head><body>
<header><a href="{prefix}index.html">{html.escape(s['name'])}</a></header>
<main><p class="pr">{html.escape(cfg['compliance']['pr_label'])}</p>{body}</main>
<footer>© {html.escape(s['name'])} ／ 当サイトはアフィリエイトプログラムに参加しています。 ／ <a href="{prefix}privacy.html">プライバシーポリシー</a></footer></body></html>"""


def _aff_links(body_md: str, slug: str) -> str:
    def repl(m: re.Match) -> str:
        pid, label = m.group(1), (m.group(2) or "公式サイトを見る")
        return (f'<a class="cta" href="../go/{pid}.html?from={slug}" rel="sponsored noopener" '
                f"onclick=\"gtag('event','affiliate_click',{{program_id:'{pid}',article:'{slug}',transport_type:'beacon'}})\">{html.escape(label)}</a>")
    return re.sub(r"\[\[aff:([a-zA-Z0-9_-]+)(?:\|([^\]]+))?\]\]", repl, body_md)


def _related(me: dict, all_articles: list[dict], n: int = 3) -> str:
    others = [a for a in all_articles if a["slug"] != me["slug"]]
    others.sort(key=lambda a: a["date"], reverse=True)  # 新しい順
    others.sort(key=lambda a: a["program_id"] != me["program_id"])  # 同じ案件の記事を優先（安定ソート）
    picks = others[:n]
    if not picks:
        return ""
    items = "".join(f'<li><a href="{a["slug"]}.html">{html.escape(a["title"])}</a></li>' for a in picks)
    return f'<nav class="related"><p>あわせて読みたい</p><ul>{items}</ul></nav>'


def run() -> int:
    cfg = load_config()
    s = cfg["site"]
    base = s["url"].rstrip("/")
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    write_text(SITE_DIR / "style.css", CSS)
    write_text(SITE_DIR / ".nojekyll", "")

    articles = []
    for path in sorted(ARTICLES_DIR.glob("*.md")):
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        articles.append({"slug": str(meta.get("slug") or path.stem), "title": meta.get("title", path.stem),
                         "desc": meta.get("description", ""), "date": str(meta.get("date", "")),
                         "updated": str(meta.get("updated", meta.get("date", ""))),
                         "program_id": meta.get("program_id", ""), "body": body})

    for a in articles:
        md = markdown.Markdown(extensions=["tables", "fenced_code", "toc"], extension_configs={"toc": {"toc_depth": "2"}})
        body_html = md.convert(_aff_links(a["body"], a["slug"]))
        toc = f'<nav class="toc"><p>目次</p>{md.toc}</nav>' if md.toc_tokens else ""
        url = f"{base}/articles/{a['slug']}.html"
        jsonld = [
            {"@context": "https://schema.org", "@type": "Article", "headline": a["title"], "description": a["desc"],
             "datePublished": a["date"], "dateModified": a["updated"], "mainEntityOfPage": url, "inLanguage": "ja",
             "author": {"@type": "Organization", "name": f"{s['name']} {s.get('author', '')}".strip()},
             "publisher": {"@type": "Organization", "name": s["name"]}},
            {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": s["name"], "item": f"{base}/"},
                {"@type": "ListItem", "position": 2, "name": a["title"], "item": url}]},
        ]
        updated = f" ／ 更新 {a['updated']}" if a["updated"] != a["date"] else ""
        page = (f"<h1>{html.escape(a['title'])}</h1>"
                f"<p class=\"meta\">公開 {a['date']}{updated} ／ {html.escape(s.get('author', ''))}</p>"
                f"{toc}{body_html}{_related(a, articles)}")
        write_text(SITE_DIR / "articles" / f"{a['slug']}.html",
                   _page(cfg, f"{a['title']}｜{s['name']}", a["desc"], page, "../",
                         path=f"articles/{a['slug']}.html", og_type="article", jsonld=jsonld))

    # 広告リンクの中継ページ（クリック計測 → 広告URLへ移動）。検索結果には出さない
    for p in cfg["programs"]:
        url = json.dumps(p["url"])
        body = (f"<p>{html.escape(p['name'])} の公式サイトへ移動します…</p>"
                f"<p><a href=\"{html.escape(p['url'])}\" rel=\"sponsored noopener\">移動しない場合はこちら</a></p>"
                f"<script>var a=new URLSearchParams(location.search).get('from')||'direct',d=false;"
                f"function go(){{if(!d){{d=true;location.replace({url})}}}}"
                f"gtag('event','affiliate_redirect',{{program_id:'{p['id']}',article:a,transport_type:'beacon',event_callback:go}});"
                f"setTimeout(go,1200);</script>")
        write_text(SITE_DIR / "go" / f"{p['id']}.html", _page(cfg, p["name"], "", body, "../", path=f"go/{p['id']}.html", noindex=True))

    name = html.escape(s["name"])
    privacy = f"""<h1>プライバシーポリシー</h1>
<h2>アクセス解析ツールについて</h2>
<p>{name}（以下「当サイト」）は、Googleによるアクセス解析ツール「Googleアナリティクス」を利用しています。Googleアナリティクスはデータの収集のためにCookieを使用します。このデータは匿名で収集されており、個人を特定するものではありません。</p>
<p>この機能はブラウザの設定でCookieを無効にすることで、収集を拒否できます。詳しくは<a href="https://marketingplatform.google.com/about/analytics/terms/jp/" rel="noopener">Googleアナリティクス利用規約</a>および<a href="https://policies.google.com/technologies/partner-sites?hl=ja" rel="noopener">Googleのポリシーと規約</a>をご覧ください。</p>
<h2>広告について</h2>
<p>当サイトは、A8.netなどのアフィリエイトプログラムに参加しています。記事内のリンクから商品・サービスを申し込むと、当サイトが広告主から報酬を受け取る場合があります。広告リンクを経由した場合、ASP・広告主がCookie等を用いて成果を計測することがあります。</p>
<p>記事の内容は、公式情報などをもとに当サイトが独自に作成しています。</p>
<h2>免責事項</h2>
<p>掲載情報は記事公開時点のものです。料金・仕様などの最新情報は、各サービスの公式サイトでご確認ください。</p>"""
    write_text(SITE_DIR / "privacy.html", _page(cfg, f"プライバシーポリシー｜{s['name']}", f"{s['name']}のプライバシーポリシー", privacy, "", path="privacy.html"))

    items = "".join(f'<li><a href="articles/{a["slug"]}.html">{html.escape(a["title"])}</a><div class="meta">{a["date"]} {html.escape(a["desc"])}</div></li>'
                    for a in sorted(articles, key=lambda a: a["date"], reverse=True))
    site_ld = [{"@context": "https://schema.org", "@type": "WebSite", "name": s["name"], "url": f"{base}/", "inLanguage": "ja"}]
    intro = f"<p>{html.escape(cfg['niche'])}を、公式情報と仕様をもとに比較・解説します。</p>"
    write_text(SITE_DIR / "index.html", _page(cfg, f"{s['name']}｜{cfg['niche']}", f"{cfg['niche']}を、公式情報と仕様をもとに解説するサイトです。",
                                              f"<h1>{name}</h1>{intro}<h2>新着記事</h2><ul class=\"list\">{items}</ul>", "", jsonld=site_ld))

    urls = f"<url><loc>{base}/</loc></url>" + "".join(
        f"<url><loc>{base}/articles/{a['slug']}.html</loc><lastmod>{a['updated']}</lastmod></url>" for a in articles)
    write_text(SITE_DIR / "sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
    # robots.txt はドメイン直下にしか効かない（github.io のサブパスでは無効）ため作らない。
    # 中継ページは noindex、サイトマップは Search Console から送信する。
    print(f"[実装] サイト生成: 記事 {len(articles)} 本 → {SITE_DIR.relative_to(ROOT)}/")
    return len(articles)
