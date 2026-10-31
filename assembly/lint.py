"""Record lint: validation errors and warnings across profiles and creations. Read-only."""
import json
from pathlib import Path
from typing import Dict, List, Tuple

from .kinds import Kind, validate_fields
from .records import list_ids, load


def lint(root: Path, kinds: Dict[str, Kind]) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
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
    cdir = Path(root) / "creations"
    for cp in sorted(cdir.glob("*.json")) if cdir.exists() else []:
        c = json.loads(cp.read_text())
        if c.get("state") == "partial":
            warnings.append("%s: creation is partial (resume it: failed or pending steps remain)" % c["id"])
    return errors, warnings
