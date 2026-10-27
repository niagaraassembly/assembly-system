"""ID minting. Only the Assembly System mints IDs; they are never reused."""
import json
import os
import re
import time
from pathlib import Path
from typing import Tuple

_ID_RE = re.compile(r"^([A-Z]+)-(\d{4,})$")


def parse_id(s: str) -> Tuple[str, int]:
    m = _ID_RE.match(s or "")
    if not m:
        raise ValueError("not an Assembly ID: %r" % (s,))
    return m.group(1), int(m.group(2))


def _highest_existing(root: Path, prefix: str) -> int:
    best = 0
    for p in (root / "profiles").glob("*/%s-*.json" % prefix):
        try:
            best = max(best, parse_id(p.stem)[1])
        except ValueError:
            continue
    return best


def mint(root: Path, prefix: str) -> str:
    """Return the next ID for prefix. Safe across threads and processes via a lock file."""
    reg = Path(root) / "registry"
    reg.mkdir(parents=True, exist_ok=True)
    lock, counters = reg / ".lock", reg / "counters.json"
    deadline = time.time() + 10
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.time() > deadline:
                raise RuntimeError("could not take the ID lock: %s (remove it if no creation is running)" % lock)
            time.sleep(0.005)
    try:
        data = json.loads(counters.read_text()) if counters.exists() else {}
        n = max(int(data.get(prefix, 0)), _highest_existing(Path(root), prefix)) + 1
        data[prefix] = n
        tmp = counters.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")
        os.replace(str(tmp), str(counters))
        return "%s-%04d" % (prefix, n)
    finally:
        os.close(fd)
        os.unlink(str(lock))
