from dataclasses import dataclass

from app.services.diff_parser import ParsedFile
from app.services.github import FileChange, GitHubClient
from app.services.prompt_limits import (
    MAX_CONTEXT_LINES,
    MAX_DIFF_LINES,
    MAX_IMPORT_LINES,
    merge_context_regions,
    truncate_lines,
)


@dataclass
class FileContext:
    filename: str
    status: str
    full_content: str | None
    diff_summary: str
    surrounding_context: str
    imports_and_definitions: str


def _extract_imports_and_definitions(content: str) -> str:
    if not content:
        return ""

    lines = content.splitlines()
    relevant: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(
            stripped.startswith(kw)
            for kw in (
                "import ", "from ", "require(", "const ", "let ", "var ",
                "package ", "using ", "#include", "use ", "mod ",
            )
        ):
            relevant.append(line)
        elif stripped.startswith(
            ("class ", "def ", "function ", "interface ", "type ", "enum ", "struct ", "pub fn", "pub struct")
        ):
            relevant.append(line)
        elif stripped.startswith("@") or stripped.startswith("export "):
            relevant.append(line)

        if len(relevant) >= MAX_IMPORT_LINES:
            break

    return "\n".join(relevant)


def _build_surrounding_context(full_content: str | None, parsed: ParsedFile) -> str:
    if not full_content:
        return ""

    lines = full_content.splitlines()
    changed_line_nums = {cl.line_number for cl in parsed.added_lines if cl.line_number}
    if not changed_line_nums:
        return ""

    regions = merge_context_regions(changed_line_nums)
    snippets: list[str] = []

    for start_line, end_line in regions:
        mid = (start_line + end_line) // 2
        ctx_start = max(0, mid - MAX_CONTEXT_LINES - 1)
        ctx_end = min(len(lines), mid + MAX_CONTEXT_LINES)
        region_lines = set(range(start_line, end_line + 1))

        snippet_lines = []
        for i in range(ctx_start, ctx_end):
            marker = ">>>" if (i + 1) in region_lines else "   "
            snippet_lines.append(f"{marker} {i + 1:4d} | {lines[i]}")

        label = f"lines {start_line}-{end_line}" if start_line != end_line else f"line {start_line}"
        snippets.append(f"--- Around {label} ---\n" + "\n".join(snippet_lines))

    return "\n\n".join(snippets)


def _build_diff_summary(parsed: ParsedFile) -> str:
    diff_lines = []
    for hunk in parsed.hunks:
        diff_lines.append(
            f"@@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@"
        )
        for line in hunk.lines:
            prefix = "+" if line.change_type == "add" else "-" if line.change_type == "delete" else " "
            diff_lines.append(f"{prefix}{line.content}")
    return truncate_lines("\n".join(diff_lines), MAX_DIFF_LINES)


class ContextBuilder:
    def __init__(self, github: GitHubClient):
        self.github = github

    async def build_contexts(
        self,
        owner: str,
        repo: str,
        head_sha: str,
        files: list[FileChange],
        parsed_files: list[ParsedFile],
    ) -> list[FileContext]:
        parsed_map = {pf.filename: pf for pf in parsed_files}
        contexts: list[FileContext] = []

        for fc in files:
            if fc.status == "removed" or not fc.patch:
                continue

            parsed = parsed_map.get(fc.filename)
            if not parsed:
                continue

            # Skip fetching huge files — diff + regions is enough
            fetch_content = (fc.additions + fc.deletions) < 500
            full_content = None
            if fetch_content:
                raw = await self.github.get_file_content(owner, repo, fc.filename, head_sha)
                if raw and len(raw) < 50_000:
                    full_content = raw

            contexts.append(
                FileContext(
                    filename=fc.filename,
                    status=fc.status,
                    full_content=full_content,
                    diff_summary=_build_diff_summary(parsed),
                    surrounding_context=_build_surrounding_context(full_content, parsed),
                    imports_and_definitions=_extract_imports_and_definitions(full_content or ""),
                )
            )

        return contexts
