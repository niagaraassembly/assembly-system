"""Handback: read machine-flows run records and update the Assembly System's records. Read-only on machine-flows.

A run is matched to a record by the `as:<ID>` tag in the run's input.md (the copy of the handoff document).
Unreadable runs are skipped and counted, never fatal. `answered` is set only by the owner (`confirm`).
"""
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .frontmatter import parse_frontmatter  # re-exported for callers
from .kinds import Kind
from .records import add_event, list_ids, load, save

STATUS_MAP = {"queued": "dispatched", "running": "running", "waiting-approval": "running",
              "done": "awaiting-confirmation", "failed": "failed", "cancelled": "failed"}
_TOUCHABLE = ("dispatched", "running", "awaiting-confirmation", "failed")


def find_runs(runs_root: Path, ref: str) -> Tuple[List[Dict[str, Any]], int]:
    """Runs whose input carries tag as:<ref>, oldest first, plus how many run folders could not be read."""
    runs_root = Path(runs_root)
    if not runs_root.is_dir():
        return [], 0
    found: List[Dict[str, Any]] = []
    skipped = 0
    for run_md in runs_root.rglob("run.md"):
        try:
            tags = parse_frontmatter((run_md.parent / "input.md").read_text(encoding="utf-8")).get("tags", [])
            if ("as:" + ref) not in tags:
                continue
            fm = parse_frontmatter(run_md.read_text(encoding="utf-8"))
            found.append({"run_id": fm.get("id", run_md.parent.name), "status": fm.get("status", ""),
                          "machine": fm.get("machine", ""), "tool": fm.get("tool", ""),
                          "actual_tool": fm.get("actual_tool", ""), "created": fm.get("created", ""),
                          "updated": fm.get("updated", "")})
        except (OSError, ValueError, UnicodeDecodeError):
            skipped += 1
    found.sort(key=lambda r: (r["created"], r["run_id"]))
    return found, skipped


def apply_handback(root: Path, kinds: Dict[str, Kind], runs_root: Path, dry_run: bool = False) -> List[str]:
    """Update records from their latest run. Returns one log line per change; repeat calls change nothing.
    With dry_run it only reports."""
    log: List[str] = []
    for kind in kinds.values():
        for id in list_ids(root, kind.name):
            rec = load(root, id, kinds)
            if rec.get("status") not in _TOUCHABLE:
                continue
            runs, _ = find_runs(runs_root, id)
            if not runs:
                continue
            latest = runs[-1]
            new_status = STATUS_MAP.get(latest["status"])
            if not new_status or new_status == rec["status"]:
                continue
            old = rec["status"]
            rec["status"] = new_status
            if dry_run:
                log.append("%s: %s -> %s (run %s)" % (id, old, new_status, latest["run_id"]))
                continue
            rec["last_run"] = {k: latest[k] for k in ("run_id", "status", "machine", "tool", "actual_tool")}
            add_event(rec, "handback", "run %s %s on %s via %s" % (latest["run_id"], latest["status"], latest["machine"], latest["actual_tool"] or latest["tool"]))
            save(root, rec)
            log.append("%s: %s -> %s (run %s)" % (id, old, new_status, latest["run_id"]))
    return log
