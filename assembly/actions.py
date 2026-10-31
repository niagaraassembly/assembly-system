"""Record actions that move status: confirm and dispatch. Shared by the CLI and any front end, so no caller edits records itself."""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .change import ChangeError, expect_rev
from .create import _applies, _creation_path, release_held
from .handoff import emit_for_step
from .kinds import Kind
from .records import add_event, load, save


def _load(root: Path, kinds: Dict[str, Kind], id: str) -> Dict[str, Any]:
    try:
        return load(root, id, kinds)
    except (ValueError, KeyError, OSError):
        raise ChangeError(["%s: no such record" % id])


def confirm_record(root: Path, kinds: Dict[str, Kind], id: str, actor: str = "owner", expected_rev: Any = None) -> Dict[str, Any]:
    """The owner accepts a finished run. Only a record awaiting confirmation can be confirmed, and only once."""
    rec = _load(root, kinds, id)
    expect_rev(rec, expected_rev)
    if rec["status"] != "awaiting-confirmation":
        raise ChangeError(["%s is %s, not awaiting-confirmation; only the owner confirms a finished run" % (id, rec["status"])])
    rec["status"] = "answered"
    add_event(rec, "confirmed", actor)
    save(root, rec)
    return rec


def dispatch_record(root: Path, kinds: Dict[str, Kind], id: str, outbox: Path, actor: str = "dispatch command",
                    expected_rev: Any = None) -> List[Path]:
    """Write the task document(s) for a record. A new record becomes `dispatched`; rewriting identical content is a no-op."""
    rec = _load(root, kinds, id)
    expect_rev(rec, expected_rev)
    if rec["status"] == "retired":
        raise ChangeError(["%s is retired; nothing is dispatched for a retired record" % id])
    kind = kinds[rec["kind"]]
    steps = [s for s in kind.steps if s["do"] == "handoff" and _applies(s, rec["fields"])]
    if not steps:
        raise ChangeError(["nothing to dispatch for %s (no handoff step applies)" % id])
    cp = _creation_path(root, id)
    if cp.exists() and any(s["status"] == "held" for s in json.loads(cp.read_text(encoding="utf-8"))["steps"]):
        c = release_held(root, kinds, id, Path(outbox))          # a captured draft: release its held steps
        bad = [s["detail"] for s in c["steps"] if s["status"] in ("failed", "pending")]
        if bad:
            raise ChangeError(["task document was not written (%s)" % "; ".join(bad)])
        return [Path(s["detail"]) for s in c["steps"] if s["do"] == "handoff" and s["status"] == "done"]
    paths = [emit_for_step(root, rec, kind, s, Path(outbox)) for s in steps]
    rec = _load(root, kinds, id)
    if rec["status"] == "new":
        rec["status"] = "dispatched"
        add_event(rec, "dispatched", actor)
        save(root, rec)
    return paths
