from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["blog"])


BASE_DIR = Path(__file__).resolve().parents[3]
BLOG_DIR = BASE_DIR / "app" / "web" / "blog_posts"


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")


def _extract_meta(content: str) -> tuple[str, str, str]:
    """
    Espera un archivo HTML con <!--META--> ... JSON-like ... <!--/META-->
    con campos: title, description, date
    Si no hay meta, devuelve defaults desde el filename.
    """
    title = "Post"
    description = ""
    date = ""
    m = re.search(r"<!--META-->(.*?)<!--/META-->", content, re.DOTALL)
    if m:
        block = m.group(1)
        t = re.search(r'title:\s*"([^"]+)"', block)
        d = re.search(r'description:\s*"([^"]+)"', block)
        f = re.search(r'date:\s*"([^"]+)"', block)
        if t: title = t.group(1)
        if d: description = d.group(1)
        if f: date = f.group(1)
    return title, description, date


def _list_posts() -> list[dict]:
    if not BLOG_DIR.exists():
        return []
    posts = []
    for path in sorted(BLOG_DIR.glob("*.html")):
        slug = path.stem
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        title, description, date = _extract_meta(content)
        posts.append({
            "slug": slug,
            "title": title,
            "description": description,
            "date": date,
        })
    # Orden por fecha desc si hay, si no por slug
    posts.sort(key=lambda p: (p["date"] or "", p["slug"]), reverse=True)
    return posts


_BLOG_INDEX_TEMPLATE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Blog — StripeReview</title>
<meta name="description" content="Guías y recursos sobre conciliación de payouts de Stripe, contabilidad y operativa para e-commerce y SaaS." />
<link rel="canonical" href="/blog" />
<style>
body { font-family: Inter, system-ui, sans-serif; background: #0b1020; color: #eef2ff; margin: 0; line-height: 1.6; }
.container { max-width: 720px; margin: 0 auto; padding: 40px 24px 80px; }
header a { color: #7c9cff; text-decoration: none; font-weight: 600; }
h1 { font-size: 32px; margin: 32px 0 8px; }
.sub { color: #aab6e8; margin: 0 0 40px; }
.post { border-bottom: 1px solid #2a3766; padding: 20px 0; }
.post:last-child { border-bottom: none; }
.post h2 { margin: 0 0 6px; font-size: 20px; }
.post h2 a { color: #eef2ff; text-decoration: none; }
.post h2 a:hover { color: #7c9cff; }
.post p { margin: 4px 0; color: #aab6e8; font-size: 14px; }
.post .date { font-size: 12px; color: #7c9cff; text-transform: uppercase; letter-spacing: 0.5px; }
</style>
</head>
<body>
<div class="container">
<header><a href="/">← StripeReview</a></header>
<h1>Blog</h1>
<p class="sub">Guías prácticas sobre conciliación de Stripe, contabilidad y herramientas.</p>
__POSTS__
</div>
</body>
</html>
"""

_POST_WRAPPER_TEMPLATE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>__TITLE__ — StripeReview</title>
<meta name="description" content="__DESCRIPTION__" />
<link rel="canonical" href="__CANONICAL__" />
<meta property="og:title" content="__TITLE__" />
<meta property="og:description" content="__DESCRIPTION__" />
<meta property="og:type" content="article" />
<style>
body { font-family: Inter, system-ui, sans-serif; background: #0b1020; color: #eef2ff; margin: 0; line-height: 1.7; }
.container { max-width: 720px; margin: 0 auto; padding: 40px 24px 80px; }
header a { color: #7c9cff; text-decoration: none; font-weight: 600; }
h1 { font-size: 32px; margin: 32px 0 12px; line-height: 1.25; }
h2 { font-size: 22px; margin: 36px 0 12px; }
h3 { font-size: 18px; margin: 28px 0 10px; }
p, li { color: #dce2ff; }
a { color: #7c9cff; }
code { background: #172042; padding: 2px 6px; border-radius: 4px; font-size: 0.92em; }
pre { background: #172042; padding: 14px; border-radius: 8px; overflow-x: auto; }
pre code { background: transparent; padding: 0; }
.date { color: #7c9cff; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
.cta {
    background: #172042; border: 1px solid #2a3766; border-radius: 14px;
    padding: 24px; margin: 32px 0; text-align: center;
}
.cta a {
    display: inline-block; background: #5c7cff; color: white; padding: 10px 24px;
    border-radius: 10px; text-decoration: none; font-weight: 600; margin-top: 8px;
}
blockquote { border-left: 3px solid #5c7cff; padding: 4px 16px; margin: 20px 0; color: #aab6e8; }
table { width: 100%; border-collapse: collapse; margin: 20px 0; }
th, td { padding: 10px; border-bottom: 1px solid #2a3766; text-align: left; }
th { background: #172042; }
</style>
</head>
<body>
<div class="container">
<header><a href="/blog">← Volver al blog</a></header>
__DATE__
<h1>__TITLE__</h1>
__CONTENT__
<div class="cta">
<strong>¿Tienes payouts de Stripe que te dan dolores de cabeza?</strong>
<p>Prueba StripeReview gratis. Sube tu CSV y ve qué payouts cuadran y cuáles no.</p>
<a href="/#register">Crear cuenta gratis</a>
</div>
</div>
</body>
</html>
"""


@router.get("/blog", response_class=HTMLResponse)
def blog_index(request: Request):
    posts = _list_posts()
    if not posts:
        posts_html = '<p class="sub">Aún no hay posts publicados.</p>'
    else:
        posts_html = "\n".join([
            f'''<div class="post">
  {"<div class='date'>" + p["date"] + "</div>" if p["date"] else ""}
  <h2><a href="/blog/{p["slug"]}">{p["title"]}</a></h2>
  <p>{p["description"]}</p>
</div>'''
            for p in posts
        ])
    html = _BLOG_INDEX_TEMPLATE.replace("__POSTS__", posts_html)
    return HTMLResponse(html)


@router.get("/blog/{slug}", response_class=HTMLResponse)
def blog_post(slug: str, request: Request):
    safe_slug = _slugify(slug)
    path = BLOG_DIR / f"{safe_slug}.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Post no encontrado")
    raw = path.read_text(encoding="utf-8")
    title, description, date = _extract_meta(raw)
    # Quitar el bloque META del contenido visible
    content = re.sub(r"<!--META-->.*?<!--/META-->", "", raw, flags=re.DOTALL).strip()
    date_html = f'<div class="date">{date}</div>' if date else ''
    canonical = f"/blog/{safe_slug}"
    html = (_POST_WRAPPER_TEMPLATE
        .replace("__TITLE__", title)
        .replace("__DESCRIPTION__", description)
        .replace("__CANONICAL__", canonical)
        .replace("__DATE__", date_html)
        .replace("__CONTENT__", content))
    return HTMLResponse(html)
