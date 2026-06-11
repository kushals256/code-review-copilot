from dataclasses import dataclass

from app.services.diff_parser import ParsedFile
from app.services.github import FileChange, GitHubClient


@dataclass
class FileContext:
    filename: str
    status: str
    full_content: str | None
    diff_summary: str
    surrounding_context: str
    imports_and_definitions: str


CONTEXT_LINES = 15


def _extract_imports_and_definitions(content: str, language_hint: str) -> str:
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
        elif stripped.startswith(("class ", "def ", "function ", "interface ", "type ", "enum ", "struct ", "pub fn", "pub struct")):
            relevant.append(line)
        elif stripped.startswith("@") or stripped.startswith("export "):
            relevant.append(line)

    return "\n".join(relevant[:40])


def _build_surrounding_context(
    full_content: str | None, parsed: ParsedFile
) -> str:
    if not full_content:
        return ""

    lines = full_content.splitlines()
    changed_line_nums = {cl.line_number for cl in parsed.added_lines if cl.line_number}
    if not changed_line_nums:
        return ""

    snippets: list[str] = []
    for line_num in sorted(changed_line_nums):
        start = max(0, line_num - CONTEXT_LINES - 1)
        end = min(len(lines), line_num + CONTEXT_LINES)
        snippet_lines = []
        for i in range(start, end):
            marker = ">>>" if (i + 1) in changed_line_nums else "   "
            snippet_lines.append(f"{marker} {i + 1:4d} | {lines[i]}")
        snippets.append(f"--- Around line {line_num} ---\n" + "\n".join(snippet_lines))

    return "\n\n".join(snippets)


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

            full_content = await self.github.get_file_content(
                owner, repo, fc.filename, head_sha
            )
            parsed = parsed_map.get(fc.filename)
            if not parsed:
                continue

            diff_lines = []
            for hunk in parsed.hunks:
                diff_lines.append(
                    f"@@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@"
                )
                for line in hunk.lines:
                    prefix = "+" if line.change_type == "add" else "-" if line.change_type == "delete" else " "
                    diff_lines.append(f"{prefix}{line.content}")

            ext = fc.filename.rsplit(".", 1)[-1] if "." in fc.filename else ""
            contexts.append(
                FileContext(
                    filename=fc.filename,
                    status=fc.status,
                    full_content=full_content,
                    diff_summary="\n".join(diff_lines),
                    surrounding_context=_build_surrounding_context(full_content, parsed),
                    imports_and_definitions=_extract_imports_and_definitions(
                        full_content or "", ext
                    ),
                )
            )

        return contexts
