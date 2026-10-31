"""Bundles: questions grouped by region and cadence, preview only.

A bundle is defined by its combination of metadata, not by question count, so a single-question bundle is
valid (D27). Key: (region, cadence, intake, origin, sensitivity, trust, effort); sources are not part of it.
Different keys never share a bundle; a group over CAP splits into numbered parts, deterministically.
Fields a question does not carry (v0 questions have no `effort`) stay None in the key and are never invented.
`plan` reads records and writes nothing. Retired and answered questions are excluded with a reason, never dropped silently.
"""
import hashlib
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from .kinds import Kind
from .period import week_id
from .records import list_ids, load

CAP = 12
KEY_FIELDS = ("region", "cadence", "intake", "origin", "sensitivity", "trust", "effort")
EXCLUDED_STATUS = {"retired": "retired", "answered": "already answered"}


def bundle_key(fields: Dict[str, Any]) -> Dict[str, Optional[str]]:
    return {k: (fields.get(k) or None) for k in KEY_FIELDS}


def due(cadence: Optional[str], on: date) -> bool:
    if cadence == "daily":
        return True
    if cadence == "weekly":
        return on.weekday() == 6          # Sunday starts the news week
    if cadence == "monthly":
        return on.day == 1
    return True                           # once, or not stated: due whenever planned


def _key_str(key: Dict[str, Optional[str]]) -> str:
    return "|".join("%s=%s" % (k, key[k] or "") for k in KEY_FIELDS)


def plan(root: Path, kinds: Dict[str, Kind], on: date, only_due: bool = False, cap: int = CAP) -> Dict[str, Any]:
    groups: Dict[str, Dict[str, Any]] = {}
    excluded: List[Dict[str, str]] = []
    for id in list_ids(root, "question"):
        rec = load(root, id, kinds)
        reason = EXCLUDED_STATUS.get(rec["status"])
        if reason:
            excluded.append({"id": id, "reason": reason})
            continue
        key = bundle_key(rec["fields"])
        is_due = due(rec["fields"].get("cadence"), on)
        if only_due and not is_due:
            continue
        g = groups.setdefault(_key_str(key), {"key": key, "members": []})
        g["members"].append({"id": id, "due": is_due})
    bundles = []
    for ks in sorted(groups):
        g = groups[ks]
        members = sorted(g["members"], key=lambda m: m["id"])
        chunks = [members[i:i + cap] for i in range(0, len(members), cap)]
        for n, chunk in enumerate(chunks, 1):
            bundles.append({"key": g["key"], "key_id": "bk-" + hashlib.sha1(("%s#%d" % (ks, n)).encode()).hexdigest()[:8],
                            "part": n, "of": len(chunks), "period": week_id(on), "members": chunk,
                            "due": any(m["due"] for m in chunk)})
    return {"on": on.isoformat(), "period": week_id(on), "bundles": bundles, "excluded": sorted(excluded, key=lambda x: x["id"])}
