"""Kind registry: what each kind of new thing must and may carry. Data lives in kinds/*.json."""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

FIELD_TYPES = ("text", "enum", "link", "list", "date", "int", "bool")
_ID_RE = re.compile(r"^([A-Z]+)-(\d{4,})$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Field:
    name: str
    type: str
    required: bool = False
    values: List[str] = field(default_factory=list)
    target: Optional[str] = None          # kind name a link points at
    target_prefix: Optional[str] = None   # resolved from target by load_kinds
    description: str = ""
    pattern: Optional[str] = None         # text fields: the whole value must match this regex


@dataclass
class Kind:
    name: str
    prefix: str
    description: str
    fields: List[Field]
    steps: List[Dict[str, Any]]

    def field(self, name: str) -> Optional[Field]:
        for f in self.fields:
            if f.name == name:
                return f
        return None


def load_kinds(kinds_dir: Path) -> Dict[str, Kind]:
    kinds: Dict[str, Kind] = {}
    for path in sorted(Path(kinds_dir).glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        fields = []
        for f in raw["fields"]:
            if f["type"] not in FIELD_TYPES:
                raise ValueError("%s: field %s has unknown type %s" % (path.name, f["name"], f["type"]))
            fields.append(Field(name=f["name"], type=f["type"], required=bool(f.get("required")),
                                values=list(f.get("values", [])), target=f.get("target"),
                                description=f.get("description", ""), pattern=f.get("pattern")))
        kinds[raw["kind"]] = Kind(raw["kind"], raw["prefix"], raw.get("description", ""), fields, list(raw.get("steps", [])))
    prefixes = {}
    for k in kinds.values():
        if k.prefix in prefixes:
            raise ValueError("duplicate prefix %s (%s, %s)" % (k.prefix, prefixes[k.prefix], k.name))
        prefixes[k.prefix] = k.name
    for k in kinds.values():
        for f in k.fields:
            if f.target:
                if f.target not in kinds:
                    raise ValueError("%s.%s links to unknown kind %s" % (k.name, f.name, f.target))
                f.target_prefix = kinds[f.target].prefix
    return kinds


def validate_fields(kind: Kind, values: Dict[str, Any], draft: bool = False) -> List[str]:
    """Return error strings that name the field; empty list means valid."""
    errors: List[str] = []
    if draft and kind.name != "question":
        errors.append("draft capture is only available for questions")
    known = {f.name for f in kind.fields}
    for name in values:
        if name not in known:
            errors.append("%s: unknown field for kind %s" % (name, kind.name))
    for f in kind.fields:
        if f.name not in values or values[f.name] in (None, "", []):
            if f.required and (not draft or f.name == "text"):
                errors.append("%s: required" % f.name)
            continue
        v = values[f.name]
        if isinstance(v, str):
            try:
                v.encode("utf-8")
            except UnicodeError:
                errors.append("%s: must contain valid Unicode text" % f.name)
        if draft and f.name == "text" and isinstance(v, str) and not v.strip():
            errors.append("text: a question cannot be blank")
        if f.type == "text" and not isinstance(v, str):
            errors.append("%s: must be text" % f.name)
        elif f.type == "text" and f.pattern and not re.fullmatch(f.pattern, v):
            errors.append("%s: %r does not match the allowed form %s" % (f.name, v[:40], f.pattern))
        elif f.type == "enum" and v not in f.values:
            errors.append("%s: %r is not one of %s" % (f.name, v, ", ".join(f.values)))
        elif f.type == "link":
            m = _ID_RE.match(v) if isinstance(v, str) else None
            if not m or m.group(1) != f.target_prefix:
                errors.append("%s: must be an ID like %s-0001" % (f.name, f.target_prefix))
        elif f.type == "list":
            if not isinstance(v, list) or not all(isinstance(i, str) for i in v):
                errors.append("%s: must be a list of text" % f.name)
            elif f.values:
                for i in v:
                    if i not in f.values:
                        errors.append("%s: %r is not one of %s" % (f.name, i, ", ".join(f.values)))
        elif f.type == "date" and not (isinstance(v, str) and _DATE_RE.match(v)):
            errors.append("%s: must be a date like 2026-10-27" % f.name)
        elif f.type == "int" and (isinstance(v, bool) or not isinstance(v, int)):
            errors.append("%s: must be a whole number" % f.name)
        elif f.type == "bool" and not isinstance(v, bool):
            errors.append("%s: must be true or false" % f.name)
    return errors
