import re
from dataclasses import dataclass, field

from unidiff import PatchSet


@dataclass
class ChangedLine:
    line_number: int
    content: str
    change_type: str  # "add", "delete", "context"
    old_line_number: int | None = None


@dataclass
class HunkInfo:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[ChangedLine] = field(default_factory=list)


@dataclass
class ParsedFile:
    filename: str
    hunks: list[HunkInfo]
    added_lines: list[ChangedLine] = field(default_factory=list)
    deleted_lines: list[ChangedLine] = field(default_factory=list)


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _parse_manually(filename: str, patch: str) -> ParsedFile:
    """Fallback parser for GitHub-style patches when unidiff is too strict."""
    parsed = ParsedFile(filename=filename, hunks=[])
    current_hunk: HunkInfo | None = None
    old_line = 0
    new_line = 0

    for raw_line in patch.splitlines():
        hunk_match = HUNK_RE.match(raw_line)
        if hunk_match:
            if current_hunk and current_hunk.lines:
                parsed.hunks.append(current_hunk)
            old_start = int(hunk_match.group(1))
            new_start = int(hunk_match.group(3))
            old_line = old_start
            new_line = new_start
            current_hunk = HunkInfo(
                old_start=old_start,
                old_count=int(hunk_match.group(2) or 1),
                new_start=new_start,
                new_count=int(hunk_match.group(4) or 1),
            )
            continue

        if not current_hunk:
            continue

        if raw_line.startswith("+"):
            changed = ChangedLine(
                line_number=new_line,
                content=raw_line[1:],
                change_type="add",
                old_line_number=None,
            )
            current_hunk.lines.append(changed)
            parsed.added_lines.append(changed)
            new_line += 1
        elif raw_line.startswith("-"):
            changed = ChangedLine(
                line_number=0,
                content=raw_line[1:],
                change_type="delete",
                old_line_number=old_line,
            )
            current_hunk.lines.append(changed)
            parsed.deleted_lines.append(changed)
            old_line += 1
        elif raw_line.startswith(" ") or raw_line == "":
            content = raw_line[1:] if raw_line.startswith(" ") else raw_line
            changed = ChangedLine(
                line_number=new_line,
                content=content,
                change_type="context",
                old_line_number=old_line,
            )
            current_hunk.lines.append(changed)
            old_line += 1
            new_line += 1

    if current_hunk and current_hunk.lines:
        parsed.hunks.append(current_hunk)

    return parsed


def _parse_with_unidiff(filename: str, patch_text: str) -> ParsedFile | None:
    try:
        patch_set = PatchSet(patch_text)
    except Exception:
        return None

    parsed = ParsedFile(filename=filename, hunks=[])
    for patched_file in patch_set:
        for hunk in patched_file:
            hunk_info = HunkInfo(
                old_start=hunk.source_start,
                old_count=hunk.source_length,
                new_start=hunk.target_start,
                new_count=hunk.target_length,
            )
            for line in hunk:
                changed = ChangedLine(
                    line_number=line.target_line_no or 0,
                    content=line.value.rstrip("\n"),
                    change_type="add" if line.is_added else "delete" if line.is_removed else "context",
                    old_line_number=line.source_line_no,
                )
                hunk_info.lines.append(changed)
                if line.is_added and line.target_line_no:
                    parsed.added_lines.append(changed)
                elif line.is_removed:
                    parsed.deleted_lines.append(changed)
            parsed.hunks.append(hunk_info)

    return parsed if parsed.hunks else None


def parse_patch(filename: str, patch: str) -> ParsedFile:
    if not patch:
        return ParsedFile(filename=filename, hunks=[])

    patch_text = patch if patch.startswith("---") else f"--- a/{filename}\n+++ b/{filename}\n{patch}"

    result = _parse_with_unidiff(filename, patch_text)
    if result:
        return result

    return _parse_manually(filename, patch)


def build_diff_summary(parsed_files: list[ParsedFile]) -> str:
    parts = []
    for pf in parsed_files:
        parts.append(f"### {pf.filename}")
        for hunk in pf.hunks:
            parts.append(
                f"@@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@"
            )
            for line in hunk.lines:
                prefix = "+" if line.change_type == "add" else "-" if line.change_type == "delete" else " "
                parts.append(f"{prefix}{line.content}")
        parts.append("")
    return "\n".join(parts)
