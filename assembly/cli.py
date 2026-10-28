"""The `assembly` command. Preview by default; --apply writes. Exit codes: 0 ok, 1 warnings, 2 failure."""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .change import ChangeError, apply_set, check_retire, check_supersede, plan_set, retire, supersede
from .create import CreationError, _applies, apply_create, plan_create, resume_create
from .handback import apply_handback
from .handoff import build_task, emit_for_step
from .ids import parse_id
from .kinds import Kind, load_kinds, validate_fields
from .records import add_event, list_ids, load, save

REPO = Path(__file__).resolve().parent.parent


def _coerce(kind: Kind, pairs: List[str], base: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    values, errors = dict(base), []
    for pair in pairs:
        if "=" not in pair:
            errors.append("--set %r: expected key=value" % pair)
            continue
        k, v = pair.split("=", 1)
        f = kind.field(k)
        t = f.type if f else "text"
        if t == "list":
            values.setdefault(k, [])
            if not isinstance(values[k], list):
                values[k] = [values[k]]
            values[k].append(v)
        elif t == "int":
            try:
                values[k] = int(v)
            except ValueError:
                errors.append("%s: must be a whole number" % k)
        elif t == "bool":
            if v.lower() in ("true", "yes", "1"):
                values[k] = True
            elif v.lower() in ("false", "no", "0"):
                values[k] = False
            else:
                errors.append("%s: must be true or false" % k)
        else:
            values[k] = v
    return values, errors


def _outbox(root: Path, given: Optional[str]) -> Path:
    return Path(given or os.environ.get("ASSEMBLY_OUTBOX") or (Path(root) / "outbox" / "prompts")).expanduser()


def _runs(given: Optional[str]) -> Path:
    return Path(given or os.environ.get("ASSEMBLY_RUNS") or "~/machine-flows/files/runs").expanduser()


def _summary(rec: Dict[str, Any]) -> str:
    f = rec["fields"]
    return " ".join(str(f.get("text") or f.get("name") or "").split())[:70]


def _find(root: Path, kinds: Dict[str, Kind], id: str):
    try:
        return load(root, id, kinds)
    except (ValueError, KeyError, OSError):
        return None


def cmd_kinds(a, root, kinds) -> int:
    if not a.kind:
        for k in kinds.values():
            print("%-9s %s-NNNN  %s" % (k.name, k.prefix, k.description))
        return 0
    if a.kind not in kinds:
        print("unknown kind %r" % a.kind, file=sys.stderr)
        return 2
    k = kinds[a.kind]
    print("%s (%s-NNNN): %s" % (k.name, k.prefix, k.description))
    for f in k.fields:
        extra = "one of " + ", ".join(f.values) if f.values else ("link to " + f.target if f.target else "")
        print("  %-12s %-5s %-9s %s %s" % (f.name, f.type, "required" if f.required else "", extra, f.description))
    for s in k.steps:
        print("  step: %s (%s)%s" % (s["id"], s["do"], " when %s" % s["when"] if s.get("when") else ""))
    return 0


def cmd_new(a, root, kinds) -> int:
    if a.kind not in kinds:
        print("error: unknown kind %r (known: %s)" % (a.kind, ", ".join(sorted(kinds))))
        return 2
    base = json.loads(Path(a.from_file).read_text(encoding="utf-8")) if a.from_file else {}
    values, errors = _coerce(kinds[a.kind], a.set or [], base)
    plan = plan_create(root, kinds, a.kind, values)
    errors += plan["errors"]
    if errors:
        for e in errors:
            print("error: " + e)
        return 2
    if not a.apply:
        print("would create %s (the ID is minted on --apply)" % a.kind)
        for k, v in sorted(values.items()):
            print("  %s: %s" % (k, v))
        for s in plan["steps"]:
            print("  step: %s (%s)" % (s["id"], s["do"]))
        print("preview only: add --apply to create it")
        return 0
    try:
        c = apply_create(root, kinds, a.kind, values, _outbox(root, a.outbox))
    except CreationError as e:
        for err in e.errors:
            print("error: " + err)
        return 2
    print("created %s (state: %s)" % (c["id"], c["state"]))
    for s in c["steps"]:
        print("  %-12s %-8s %s" % (s["id"], s["status"], s["detail"]))
    return 1 if c["state"] == "partial" else 0


def cmd_show(a, root, kinds) -> int:
    rec = _find(root, kinds, a.id)
    if rec is None:
        print("no such record: %s" % a.id, file=sys.stderr)
        return 2
    cp = Path(root) / "creations" / (a.id + ".json")
    print(json.dumps({"record": rec, "creation": json.loads(cp.read_text()) if cp.exists() else None}, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def cmd_list(a, root, kinds) -> int:
    for k in ([kinds[a.kind]] if a.kind in kinds else list(kinds.values())):
        for id in list_ids(root, k.name):
            rec = load(root, id, kinds)
            print("%-8s %-22s %s" % (id, rec["status"], _summary(rec)))
    return 0


def cmd_lint(a, root, kinds) -> int:
    errors, warnings = [], []
    for k in kinds.values():
        for id in list_ids(root, k.name):
            rec = load(root, id, kinds)
            for e in validate_fields(k, rec["fields"]):
                errors.append("%s: %s" % (id, e))
            for f in k.fields:
                v = rec["fields"].get(f.name)
                if f.type == "link" and v and v not in list_ids(root, f.target):
                    errors.append("%s: %s: %s does not exist" % (id, f.name, v))
                elif f.type == "link" and v:
                    target = load(root, v, kinds)
                    if f.name == "supersedes" and target["status"] != "retired":
                        warnings.append("%s: supersedes %s but %s is not retired" % (id, v, v))
                    elif f.name != "supersedes" and target["status"] == "retired" and rec["status"] != "retired":
                        warnings.append("%s: %s points at retired record %s" % (id, f.name, v))
    for cp in sorted((Path(root) / "creations").glob("*.json")) if (Path(root) / "creations").exists() else []:
        c = json.loads(cp.read_text())
        if c.get("state") == "partial":
            warnings.append("%s: creation is partial (resume it: failed or pending steps remain)" % c["id"])
    for e in errors:
        print("error: " + e)
    for w in warnings:
        print("warn: " + w)
    if not errors and not warnings:
        print("ok")
    return 2 if errors else (1 if warnings else 0)


def cmd_dispatch(a, root, kinds) -> int:
    rec = _find(root, kinds, a.id)
    if rec is None:
        print("no such record: %s" % a.id, file=sys.stderr)
        return 2
    if rec["status"] == "retired":
        print("%s is retired; nothing is dispatched for a retired record" % a.id, file=sys.stderr)
        return 2
    kind = kinds[rec["kind"]]
    steps = [s for s in kind.steps if s["do"] == "handoff" and _applies(s, rec["fields"])]
    if not steps:
        print("nothing to dispatch for %s (no handoff step applies)" % a.id, file=sys.stderr)
        return 2
    outbox = _outbox(root, a.outbox)
    for s in steps:
        if not a.apply:
            print("would write %s" % (outbox / build_task(rec, kind, s)[0]))
        else:
            path = emit_for_step(root, rec, kind, s, outbox)
            print("wrote %s" % path)
    if not a.apply:
        print("preview only: add --apply to write it")
    elif rec["status"] == "new":
        rec["status"] = "dispatched"
        add_event(rec, "dispatched", "dispatch command")
        save(root, rec)
    return 0


def _fail(e: ChangeError) -> int:
    for err in e.errors:
        print("error: " + err)
    return 2


def cmd_set(a, root, kinds) -> int:
    rec = _find(root, kinds, a.id)
    if rec is None:
        print("no such record: %s" % a.id, file=sys.stderr)
        return 2
    changes, errors = _coerce(kinds[rec["kind"]], a.set or [], {})
    if errors:
        for e in errors:
            print("error: " + e)
        return 2
    try:
        plan = plan_set(root, kinds, a.id, changes, a.unset or [])
        if plan["errors"]:
            raise ChangeError(plan["errors"])
        if not plan["diff"]:
            print("no changes")
            return 0
        for d in plan["diff"]:
            print("  %s: %s -> %s" % (d["field"], "(unset)" if d["old"] is None else d["old"], "(unset)" if d["new"] is None else d["new"]))
        if not a.apply:
            print("preview only: add --apply to change it")
            return 0
        done = apply_set(root, kinds, a.id, changes, a.unset or [], actor=a.actor)
    except ChangeError as e:
        return _fail(e)
    print("%s changed (rev %d); run `assembly dispatch %s --apply` to write a revised task document" % (a.id, done["rev"], a.id))
    return 0


def cmd_retire(a, root, kinds) -> int:
    try:
        check_retire(root, kinds, a.id)
        if not a.apply:
            print("would retire %s (%s)" % (a.id, a.reason))
            print("preview only: add --apply to retire it")
            return 0
        retire(root, kinds, a.id, a.reason, actor=a.actor)
    except ChangeError as e:
        return _fail(e)
    print("%s retired" % a.id)
    return 0


def cmd_supersede(a, root, kinds) -> int:
    try:
        check_supersede(root, kinds, a.id, a.by)
        if not a.apply:
            print("would retire %s and link %s to it (supersedes)" % (a.id, a.by))
            print("preview only: add --apply to do it")
            return 0
        supersede(root, kinds, a.id, a.by, actor=a.actor)
    except ChangeError as e:
        return _fail(e)
    print("%s retired, superseded by %s" % (a.id, a.by))
    return 0


def cmd_resume(a, root, kinds) -> int:
    try:
        c = resume_create(root, kinds, a.id, _outbox(root, a.outbox))
    except (OSError, ValueError, KeyError):
        print("no creation record for %s" % a.id, file=sys.stderr)
        return 2
    print("%s: state %s" % (c["id"], c["state"]))
    for s in c["steps"]:
        print("  %-12s %-8s %s" % (s["id"], s["status"], s["detail"]))
    return 1 if c["state"] == "partial" else 0


def cmd_handback(a, root, kinds) -> int:
    log = apply_handback(root, kinds, _runs(a.runs), dry_run=not a.apply)
    for line in log:
        print(line)
    if not log:
        print("no changes")
    if not a.apply and log:
        print("preview only: add --apply to record these")
    return 0


def cmd_confirm(a, root, kinds) -> int:
    rec = _find(root, kinds, a.id)
    if rec is None:
        print("no such record: %s" % a.id, file=sys.stderr)
        return 2
    if rec["status"] != "awaiting-confirmation":
        print("%s is %s, not awaiting-confirmation; only the owner confirms a finished run" % (a.id, rec["status"]), file=sys.stderr)
        return 2
    rec["status"] = "answered"
    add_event(rec, "confirmed", "owner")
    save(root, rec)
    print("%s answered" % a.id)
    return 0


def main(argv: Optional[List[str]] = None, root: Optional[Path] = None) -> int:
    root = Path(root or os.environ.get("ASSEMBLY_ROOT") or REPO)
    p = argparse.ArgumentParser(prog="assembly", description="Assembly System: create, dispatch and track company records.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("kinds"); s.add_argument("kind", nargs="?")
    s = sub.add_parser("new"); s.add_argument("kind"); s.add_argument("--set", action="append"); s.add_argument("--from", dest="from_file")
    s.add_argument("--outbox"); s.add_argument("--apply", action="store_true")
    s = sub.add_parser("show"); s.add_argument("id")
    s = sub.add_parser("list"); s.add_argument("kind", nargs="?")
    sub.add_parser("lint")
    s = sub.add_parser("dispatch"); s.add_argument("id"); s.add_argument("--outbox"); s.add_argument("--apply", action="store_true")
    s = sub.add_parser("set"); s.add_argument("id"); s.add_argument("--set", action="append"); s.add_argument("--unset", action="append")
    s.add_argument("--actor", default="owner"); s.add_argument("--apply", action="store_true")
    s = sub.add_parser("retire"); s.add_argument("id"); s.add_argument("--reason", required=True)
    s.add_argument("--actor", default="owner"); s.add_argument("--apply", action="store_true")
    s = sub.add_parser("supersede"); s.add_argument("id", help="the record being replaced"); s.add_argument("--by", required=True, help="the replacing record")
    s.add_argument("--actor", default="owner"); s.add_argument("--apply", action="store_true")
    s = sub.add_parser("resume"); s.add_argument("id"); s.add_argument("--outbox")
    s = sub.add_parser("handback"); s.add_argument("--runs"); s.add_argument("--apply", action="store_true")
    s = sub.add_parser("confirm"); s.add_argument("id")
    a = p.parse_args(argv)
    kinds = load_kinds(REPO / "kinds")
    return {"kinds": cmd_kinds, "new": cmd_new, "show": cmd_show, "list": cmd_list, "lint": cmd_lint,
            "dispatch": cmd_dispatch, "set": cmd_set, "retire": cmd_retire, "supersede": cmd_supersede, "resume": cmd_resume, "handback": cmd_handback, "confirm": cmd_confirm}[a.cmd](a, root, kinds)


if __name__ == "__main__":
    sys.exit(main())
