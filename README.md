# Code Review Copilot

An AI-powered GitHub code reviewer that catches bugs, explains decisions, and teaches as it reviews.

Built for Assignment 2 — handles mechanical review comments so senior engineers can focus on architecture.

## Features

| Feature | Description |
|---------|-------------|
| **PR Diff Analysis** | Fetches PRs via URL or webhook, parses unified diffs with full file context |
| **Inline Comments** | Posts comments on exact lines with issue, why it matters, and suggested fix |
| **Risk Summary** | Quality score, highest-risk changes, and merge recommendation posted to PR |
| **Convention Learning** | Extracts team coding rules from merged PR review history |
| **Severity Tagging** | Every comment tagged: `bug`, `security`, `performance`, `style`, `suggestion` |
| **Explanation Mode** | Plain-English explanations aimed at junior developers |

## Quick Start

### 1. Install dependencies

Requires **Python 3.11–3.13** (3.14 is not yet supported by all dependencies).

```bash
python3.13 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

- **GITHUB_TOKEN** — Personal access token with `repo` and `pull_requests` scopes ([create one](https://github.com/settings/tokens))
- **OPENAI_API_KEY** — OpenAI API key ([get one](https://platform.openai.com/api-keys))
- **GITHUB_WEBHOOK_SECRET** — Optional, for webhook signature verification

### 3. Run the server

```bash
python run.py
```

Open [http://localhost:8000](http://localhost:8000) for the web UI.

## Usage

### Web UI

1. Paste a GitHub PR URL (e.g. `https://github.com/owner/repo/pull/42`)
2. Click **Preview (Dry Run)** to see results without posting to GitHub
3. Click **Review & Post to GitHub** to post inline comments + risk summary

### API

**Review a PR (dry run):**
```bash
curl -X POST http://localhost:8000/api/review/dry-run \
  -H "Content-Type: application/json" \
  -d '{"pr_url": "https://github.com/owner/repo/pull/123"}'
```

**Review and post to GitHub:**
```bash
curl -X POST http://localhost:8000/api/review \
  -H "Content-Type: application/json" \
  -d '{"pr_url": "https://github.com/owner/repo/pull/123"}'
```

**Extract team conventions:**
```bash
curl -X POST http://localhost:8000/api/conventions/extract \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/owner/repo", "max_prs": 20}'
```

### GitHub Webhook (automatic reviews)

1. Go to your repo → Settings → Webhooks → Add webhook
2. **Payload URL:** `https://your-server.com/webhook/github`
3. **Content type:** `application/json`
4. **Secret:** same value as `GITHUB_WEBHOOK_SECRET` in `.env`
5. **Events:** Pull requests

The copilot auto-reviews PRs on `opened`, `synchronize`, and `reopened` events.

For local development, use [ngrok](https://ngrok.com/) to expose your server:
```bash
ngrok http 8000
```

## Architecture

```
app/
├── main.py                  # FastAPI application
├── config.py                # Environment settings
├── models/schemas.py        # Pydantic models (Severity, ReviewComment, etc.)
├── routes/
│   ├── review.py            # POST /api/review, /api/review/dry-run
│   ├── conventions.py       # POST /api/conventions/extract
│   └── webhook.py           # POST /webhook/github
├── services/
│   ├── github.py            # GitHub REST API client
│   ├── diff_parser.py       # Unified diff parsing (unidiff)
│   ├── context_builder.py   # File context (imports, surrounding lines)
│   ├── reviewer.py          # OpenAI-powered review engine
│   ├── comment_poster.py    # Formats & posts comments to GitHub
│   ├── convention_learner.py  # Extracts rules from PR history
│   └── review_pipeline.py   # Orchestrates the full review flow
└── static/                  # Web UI (HTML/CSS/JS)
```

### Review Pipeline

```
PR URL / Webhook
    ↓
Fetch PR + file diffs (GitHub API)
    ↓
Parse diffs + build file context (imports, surrounding code)
    ↓
Extract team conventions (from merged PR history)
    ↓
AI Review (OpenAI) → comments + risk summary
    ↓
Post risk summary + inline comments to GitHub
```

## Grading Criteria Mapping

| Criteria | How We Meet It |
|----------|----------------|
| **Correct Attribution** | Comments use GitHub review API with exact `path` + `line` on the RIGHT side of diff |
| **Accuracy** | AI receives full diff + surrounding context + imports, not just changed lines |
| **Consistency** | Severity enum enforced in schema; tagged in every comment |
| **Extraction** | Convention learner analyzes merged PR review comments, returns ≥3 rules |
| **Clarity** | Every comment has `explanation` field written for junior developers |

## Team Setup (5 students)

Suggested division of work:

1. **GitHub Integration** — `github.py`, `webhook.py`, `comment_poster.py`
2. **Diff & Context** — `diff_parser.py`, `context_builder.py`
3. **AI Review Engine** — `reviewer.py`, prompt engineering, severity tagging
4. **Convention Learning** — `convention_learner.py`
5. **Frontend & API** — `static/`, `routes/`, `main.py`, README, demo

## License

MIT — built for educational purposes.
