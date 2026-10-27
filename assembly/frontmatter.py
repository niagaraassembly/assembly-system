"""Flat frontmatter reader: `key: value`, double-quoted strings, inline lists. Standard library only."""
import json
from typing import Any, Dict


def _value(raw: str) -> Any:
    raw = raw.strip()
    if raw.startswith('"'):
        try:
            return json.loads(raw)
        except ValueError:
            return raw.strip('"')
    if raw.startswith("[") and raw.endswith("]"):
        return [i.strip().strip('"') for i in raw[1:-1].split(",") if i.strip()]
    return raw


def parse_frontmatter(text: str) -> Dict[str, Any]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("no frontmatter")
    out: Dict[str, Any] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError("bad frontmatter line: %r" % line[:60])
        k, v = line.split(":", 1)
        out[k.strip()] = _value(v)
    raise ValueError("frontmatter is not closed")
