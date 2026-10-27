"""Profile store: one JSON file per thing under profiles/<kind>/<ID>.json."""
import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from .ids import parse_id
from .kinds import Kind


def _now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def new_record(kind: Kind, id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    return {"schema": 1, "id": id, "kind": kind.name, "fields": dict(fields), "status": "new",
            "created": _now(), "history": []}


def add_event(rec: Dict[str, Any], event: str, detail: str = "") -> None:
    rec["history"].append({"at": _now(), "event": event, "detail": detail})


def _path(root: Path, kind_name: str, id: str) -> Path:
    parse_id(id)  # refuses anything that is not a plain ID, so no path tricks
    return Path(root) / "profiles" / kind_name / (id + ".json")


def save(root: Path, rec: Dict[str, Any]) -> Path:
    p = _path(root, rec["kind"], rec["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name("." + p.name + ".tmp")
    tmp.write_text(json.dumps(rec, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(p))
    return p


def load(root: Path, id: str, kinds: Dict[str, Kind]) -> Dict[str, Any]:
    prefix, _ = parse_id(id)
    for k in kinds.values():
        if k.prefix == prefix:
            return json.loads(_path(root, k.name, id).read_text(encoding="utf-8"))
    raise KeyError("no kind with prefix %s" % prefix)


def list_ids(root: Path, kind_name: str) -> List[str]:
    d = Path(root) / "profiles" / kind_name
    return sorted(p.stem for p in d.glob("*-*.json")) if d.exists() else []
