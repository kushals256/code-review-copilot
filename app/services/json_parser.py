import json
import re


def extract_json_text(text: str) -> str:
    text = (text or "").strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1:
        raise ValueError("No JSON object found in model response")
    if end > start:
        return text[start : end + 1]
    return text[start:]


def _repair_truncated_json(text: str) -> str:
    """Close truncated JSON by trimming a partial tail and balancing brackets."""
    trimmed = text.rstrip()

    # Drop trailing partial key/value/string
    trimmed = re.sub(r',?\s*"[^"]*":\s*"[^"]*$', "", trimmed)
    trimmed = re.sub(r',?\s*"[^"]*":\s*[^,\}\]]*$', "", trimmed)
    trimmed = re.sub(r',?\s*"[^"]*$', "", trimmed)
    trimmed = trimmed.rstrip(",")

    open_braces = trimmed.count("{") - trimmed.count("}")
    open_brackets = trimmed.count("[") - trimmed.count("]")

    if open_braces > 0 or open_brackets > 0:
        trimmed += "]" * max(0, open_brackets) + "}" * max(0, open_braces)

    return trimmed


def parse_llm_json(text: str) -> dict:
    raw = extract_json_text(text)

    for candidate in (raw, _repair_truncated_json(raw)):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue

    raise ValueError(
        "Model returned invalid JSON. Try Preview on a smaller PR or retry."
    )
