import re

# Rough chars-to-tokens ratio for budgeting
CHARS_PER_TOKEN = 4

SKIP_FILENAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Cargo.lock",
    "poetry.lock",
    "Gemfile.lock",
    "composer.lock",
}

SKIP_EXTENSIONS = {
    ".lock",
    ".min.js",
    ".min.css",
    ".map",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp4",
    ".mp3",
}

SKIP_PATH_PARTS = (
    "node_modules/",
    "dist/",
    "build/",
    ".venv/",
    "venv/",
    "__pycache__/",
    ".git/",
    "vendor/",
)

MAX_FILES = 25
MAX_DIFF_LINES = 120
MAX_CONTEXT_REGIONS = 5
MAX_CONTEXT_LINES = 10
MAX_IMPORT_LINES = 25
MAX_PR_BODY_CHARS = 2500
MAX_CONVENTION_RULES = 8
MAX_TOTAL_PROMPT_CHARS = 90_000


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def truncate_text(text: str, max_chars: int, suffix: str = "\n… [truncated]") -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - len(suffix)] + suffix


def truncate_lines(text: str, max_lines: int) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    head = max_lines * 2 // 3
    tail = max_lines - head
    omitted = len(lines) - max_lines
    return "\n".join(
        lines[:head]
        + [f"… [{omitted} lines omitted] …"]
        + lines[-tail:]
    )


def should_skip_file(filename: str) -> bool:
    base = filename.rsplit("/", 1)[-1]
    if base in SKIP_FILENAMES:
        return True
    lower = filename.lower()
    if any(part in lower for part in SKIP_PATH_PARTS):
        return True
    for ext in SKIP_EXTENSIONS:
        if lower.endswith(ext):
            return True
    return False


def file_change_score(additions: int, deletions: int) -> int:
    return additions + deletions


def merge_context_regions(
    line_nums: set[int],
    max_regions: int = MAX_CONTEXT_REGIONS,
    merge_gap: int = MAX_CONTEXT_LINES * 2,
) -> list[tuple[int, int]]:
    if not line_nums:
        return []

    sorted_nums = sorted(line_nums)
    regions: list[tuple[int, int]] = []
    start = end = sorted_nums[0]

    for num in sorted_nums[1:]:
        if num - end <= merge_gap:
            end = num
        else:
            regions.append((start, end))
            start = end = num
    regions.append((start, end))

    if len(regions) <= max_regions:
        return regions

    regions.sort(key=lambda r: (r[1] - r[0], r[1]), reverse=True)
    kept = sorted(regions[:max_regions], key=lambda r: r[0])
    return kept
