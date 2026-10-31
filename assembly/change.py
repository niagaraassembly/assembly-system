"""Changing records after creation, through the same front door: set, retire, supersede.

Every change is validated like a creation, recorded in the history (old -> new, who), and bumps `rev`,
so a revised handoff document can sit beside the earlier one. Retired records are read-only. Nothing is deleted.
"""
from pathlib import Path
from typing import Any, Dict, List

from .kinds import Kind, validate_fields
from .records import add_event, load, save


class ChangeError(ValueError):
    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _load(root: Path, kinds: Dict[str, Kind], id: str) -> Dict[str, Any]:
    try:
        return load(root, id, kinds)
    except (ValueError, KeyError, OSError):
        raise ChangeError(["%s: no such record" % id])


def expect_rev(rec: Dict[str, Any], expected: Any) -> None:
    """Refuse a change made from a stale view: the caller says which rev it loaded."""
    if expected is not None and rec.get("rev", 0) != expected:
        raise ChangeError(["%s changed since you loaded it (now rev %d, you had rev %s). Reload and try again." % (rec["id"], rec.get("rev", 0), expected)])


def _show(v: Any) -> str:
    return "(unset)" if v is None else " ".join(str(v).split())[:80]


def plan_set(root: Path, kinds: Dict[str, Kind], id: str, changes: Dict[str, Any], unset: List[str]) -> Dict[str, Any]:
    """Preview of a field change: errors and the field-by-field diff. Writes nothing."""
    rec = _load(root, kinds, id)
    kind = kinds[rec["kind"]]
    errors: List[str] = []
    if rec["status"] == "retired":
        errors.append("%s: retired records are read-only" % id)
    merged = dict(rec["fields"])
    merged.update(changes)
    for k in unset:
        if kind.field(k) is None:
            errors.append("%s: unknown field for kind %s" % (k, kind.name))
        merged.pop(k, None)
    errors += validate_fields(kind, merged)
    diff = [{"field": k, "old": rec["fields"].get(k), "new": merged.get(k)}
            for k in sorted(set(rec["fields"]) | set(merged)) if rec["fields"].get(k) != merged.get(k)]
    return {"id": id, "kind": kind.name, "errors": errors, "diff": diff, "merged": merged, "rev": rec.get("rev", 0)}


def apply_set(root: Path, kinds: Dict[str, Kind], id: str, changes: Dict[str, Any], unset: List[str],
              actor: str = "owner", expected_rev: Any = None) -> Dict[str, Any]:
    expect_rev(_load(root, kinds, id), expected_rev)
    plan = plan_set(root, kinds, id, changes, unset)
    if plan["errors"]:
        raise ChangeError(plan["errors"])
    if not plan["diff"]:
        return plan
    rec = _load(root, kinds, id)
    rec["fields"] = plan["merged"]
    rec["rev"] = rec.get("rev", 0) + 1
    add_event(rec, "changed", "; ".join("%s: %s -> %s" % (d["field"], _show(d["old"]), _show(d["new"])) for d in plan["diff"])
              + " [by %s]" % actor)
    save(root, rec)
    plan["rev"] = rec["rev"]
    return plan


def check_retire(root: Path, kinds: Dict[str, Kind], id: str) -> Dict[str, Any]:
    rec = _load(root, kinds, id)
    if rec["status"] == "retired":
        raise ChangeError(["%s: already retired" % id])
    return rec


def retire(root: Path, kinds: Dict[str, Kind], id: str, reason: str, actor: str = "owner", detail: str = "",
           expected_rev: Any = None) -> Dict[str, Any]:
    rec = check_retire(root, kinds, id)
    expect_rev(rec, expected_rev)
    rec["status"] = "retired"
    add_event(rec, "retired", "%s [by %s]" % (detail or reason, actor))
    save(root, rec)
    return rec


def check_supersede(root: Path, kinds: Dict[str, Kind], old_id: str, new_id: str):
    if old_id == new_id:
        raise ChangeError(["a record cannot supersede itself"])
    old, new = _load(root, kinds, old_id), _load(root, kinds, new_id)
    errors = []
    if old["kind"] != new["kind"]:
        errors.append("%s and %s are different kinds (%s, %s)" % (old_id, new_id, old["kind"], new["kind"]))
    elif kinds[new["kind"]].field("supersedes") is None:
        errors.append("kind %s cannot supersede (no `supersedes` field)" % new["kind"])
    for r in (old, new):
        if r["status"] == "retired":
            errors.append("%s: already retired" % r["id"])
    if new["fields"].get("supersedes") not in (None, old_id):
        errors.append("%s already supersedes %s" % (new_id, new["fields"]["supersedes"]))
    if errors:
        raise ChangeError(errors)
    return old, new


def supersede(root: Path, kinds: Dict[str, Kind], old_id: str, new_id: str, actor: str = "owner",
              expected_rev: Any = None) -> Dict[str, Any]:
    old, _ = check_supersede(root, kinds, old_id, new_id)
    expect_rev(old, expected_rev)
    apply_set(root, kinds, new_id, {"supersedes": old_id}, [], actor=actor)
    return retire(root, kinds, old_id, "", actor=actor, detail="superseded by %s" % new_id)
