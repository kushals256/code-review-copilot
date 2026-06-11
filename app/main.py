from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routes import conventions, review, webhook

app = FastAPI(
    title="Code Review Copilot",
    description="AI-powered code reviewer that catches bugs, explains decisions, and teaches as it reviews.",
    version="1.0.0",
)

app.include_router(review.router)
app.include_router(conventions.router)
app.include_router(webhook.router)

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
async def home():
    index = static_dir / "index.html"
    if index.exists():
        return index.read_text()
    return "<h1>Code Review Copilot</h1><p>Place index.html in app/static/</p>"


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "github_configured": bool(settings.github_token),
        "llm_provider": settings.llm_provider,
        "llm_model": settings.effective_model,
        "llm_configured": settings.llm_provider == "ollama" or bool(settings.effective_api_key),
    }
