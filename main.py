from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.auth import router as auth_router
from app.api.routes.billing import router as billing_router
from app.api.routes.blog import router as blog_router
from app.api.routes.clients import router as clients_router
from app.api.routes.tools import router as tools_router
from app.core.config import APP_ENV, APP_NAME, ensure_runtime_dirs

ensure_runtime_dirs()

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "app" / "web"
INDEX_PATH = WEB_DIR / "index.html"
STATIC_DIR = WEB_DIR / "static"
DEMO_FILES_DIR = BASE_DIR / "demo_files"

app = FastAPI(title=APP_NAME, version="2.0.0", docs_url="/docs", redoc_url="/redoc")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if DEMO_FILES_DIR.exists():
    app.mount("/demo-files", StaticFiles(directory=str(DEMO_FILES_DIR)), name="demo-files")

app.include_router(auth_router)
app.include_router(clients_router)
app.include_router(billing_router)
app.include_router(blog_router)
app.include_router(tools_router)


@app.get("/health")
def health():
    return {"ok": True, "status": "healthy", "app": APP_NAME, "env": APP_ENV}


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return """User-agent: *
Allow: /
Allow: /blog
Allow: /privacy
Disallow: /tools/
Disallow: /auth/
Disallow: /clients/
Disallow: /billing/
Disallow: /docs
Disallow: /redoc
Sitemap: https://stripe-review-production.up.railway.app/sitemap.xml
"""


@app.get("/sitemap.xml")
def sitemap():
    from app.api.routes.blog import _list_posts

    base_url = "https://stripe-review-production.up.railway.app"

    urls = [
        ("/", "weekly", "1.0"),
        ("/blog", "weekly", "0.9"),
        ("/privacy", "yearly", "0.3"),
    ]

    for post in _list_posts():
        urls.append((f"/blog/{post['slug']}", "monthly", "0.8"))

    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    for loc, changefreq, priority in urls:
        xml_parts.append(
            f"  <url><loc>{base_url}{loc}</loc>"
            f"<changefreq>{changefreq}</changefreq>"
            f"<priority>{priority}</priority></url>"
        )

    xml_parts.append("</urlset>")
    return PlainTextResponse("\n".join(xml_parts), media_type="application/xml")


@app.get("/privacy", include_in_schema=False)
def privacy():
    privacy_path = WEB_DIR / "privacy.html"
    if privacy_path.exists():
        return FileResponse(str(privacy_path), media_type="text/html")
    return JSONResponse({"ok": False, "message": "Privacy page not found"}, status_code=404)


@app.get("/")
def root():
    if INDEX_PATH.exists():
        return FileResponse(str(INDEX_PATH), media_type="text/html")
    return JSONResponse({"ok": True, "message": f"{APP_NAME} está funcionando", "docs": "/docs"})