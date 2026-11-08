"""The creation action: one front door for anything new.

Mints the ID, writes the profile, then runs the kind's steps. Progress is rewritten after every
step (creations/<ID>.json), so a crash leaves the true state and `resume_create` finishes the rest
without minting again.
"""
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .ids import mint
from .kinds import Kind, validate_fields
from .records import add_event, load, new_record, save


class CreationError(ValueError):
    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _applies(step: Dict[str, Any], values: Dict[str, Any]) -> bool:
    return all(values.get(k) == v for k, v in step.get("when", {}).items())


def _steps_for(kind: Kind, values: Dict[str, Any], existing: bool = False) -> List[Dict[str, Any]]:
    steps = [{"id": "write-profile", "do": "profile"}]
    if not existing:  # a thing that already exists needs no provisioning, handoff or checklist
        steps += [dict(s) for s in kind.steps if _applies(s, values)]
    return steps


def plan_create(root: Path, kinds: Dict[str, Kind], kind_name: str, values: Dict[str, Any], existing: bool = False,
                draft: bool = False) -> Dict[str, Any]:
    """Preview only: validates and lists the steps. Writes nothing and mints nothing."""
    if kind_name not in kinds:
        return {"kind": kind_name, "errors": ["unknown kind %r (known: %s)" % (kind_name, ", ".join(sorted(kinds)))],
                "steps": [], "fields": values}
    kind = kinds[kind_name]
    errors = validate_fields(kind, values, draft=draft)
    if draft and existing:
        errors.append("choose either draft capture or an existing thing")
    source = values.get("source_question")
    if source and not errors:
        try:
            parent = load(root, source, kinds)
            if parent["kind"] != "question":
                errors.append("source_question: must refer to a question")
        except (OSError, KeyError, ValueError):
            errors.append("source_question: %s does not exist" % source)
    return {"kind": kind_name, "errors": errors, "steps": _steps_for(kind, values, existing or draft), "fields": values}


def _creation_path(root: Path, id: str) -> Path:
    return Path(root) / "creations" / (id + ".json")


def _write_creation(root: Path, c: Dict[str, Any]) -> None:
    statuses = [s["status"] for s in c["steps"]]
    if any(s in ("pending", "failed") for s in statuses):
        c["state"] = "partial"
    elif "manual" in statuses:
        c["state"] = "manual-pending"
    else:
        c["state"] = "complete"
    p = _creation_path(root, c["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name("." + p.name + ".tmp")
    tmp.write_text(json.dumps(c, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(p))


def _default_emit(root, rec, kind, step, outbox):
    from .handoff import emit_for_step
    return emit_for_step(root, rec, kind, step, outbox)


def _run_handoffs(root: Path, kinds: Dict[str, Kind], c: Dict[str, Any], outbox: Path, emit: Callable) -> None:
    rec = load(root, c["id"], kinds)
    if rec.get("draft"):
        return  # a capture never executes steps, including during resume
    kind = kinds[rec["kind"]]
    for s in c["steps"]:
        if s["do"] != "handoff" or s["status"] not in ("pending", "failed"):
            continue
        try:
            path = emit(root, rec, kind, s, Path(outbox))
            s["status"], s["detail"] = "done", str(path)
            add_event(rec, "handoff-written", s["id"])
            if rec["status"] == "new":
                rec["status"] = "dispatched"
            save(root, rec)
        except Exception as e:  # recorded, not raised: the creation stays resumable
            s["status"], s["detail"] = "failed", "%s: %s" % (type(e).__name__, e)
        _write_creation(root, c)


def apply_create(root: Path, kinds: Dict[str, Kind], kind_name: str, values: Dict[str, Any],
                 outbox: Path, emit: Optional[Callable] = None, existing: bool = False,
                 draft: bool = False) -> Dict[str, Any]:
    plan = plan_create(root, kinds, kind_name, values, existing, draft=draft)
    if plan["errors"]:
        raise CreationError(plan["errors"])
    kind = kinds[kind_name]
    id = mint(root, kind.prefix)
    rec = new_record(kind, id, values)
    if draft:
        rec["draft"], rec["status"] = True, "draft"
    detail = "creation action (draft question: capture only)" if draft else (
        "creation action (already exists: profile only)" if existing else "creation action")
    add_event(rec, "created", detail)
    save(root, rec)
    c = {"id": id, "kind": kind_name, "state": "partial", "steps": []}
    for s in plan["steps"]:
        status = {"profile": "done", "handoff": "pending", "manual": "manual"}[s["do"]]
        entry = {"id": s["id"], "do": s["do"], "status": status, "detail": s.get("text", "")}
        if s.get("template"):
            entry["template"] = s["template"]
        c["steps"].append(entry)
    _write_creation(root, c)
    _run_handoffs(root, kinds, c, outbox, emit or _default_emit)
    return c


def resume_create(root: Path, kinds: Dict[str, Kind], id: str, outbox: Path, emit: Optional[Callable] = None) -> Dict[str, Any]:
    c = json.loads(_creation_path(root, id).read_text(encoding="utf-8"))
    _run_handoffs(root, kinds, c, outbox, emit or _default_emit)
    _write_creation(root, c)
    return c
