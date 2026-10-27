"""Handoff to machine-flows, version 0.

Writes a machine-flows prompt document using only the v0 key set that `mach run` accepts. The body is
deterministic: when the record has a `procedure`, the document says to run exactly those steps and nothing
else, so no interpretation is needed; otherwise it is marked as needing an agent. The link back to the
record and the handoff version travel in `tags` (as:<ID>, as-v0). Later versions replace the tags with
first-class contract keys (machine-flows NA-330).
"""
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .frontmatter import parse_frontmatter
from .kinds import Kind

HANDOFF_VERSION = 0
REQUIRED = ["mach", "type", "title", "goal", "tool", "output"]
OPTIONAL = ["permission", "path", "machine", "due", "approval", "tags", "model"]
TOOLS = ["claude", "codex", "cursor-agent", "grokcli-agent", "kiro", "muse", "auto"]
APPROVALS = ["none", "before-run", "before-apply"]
PERMISSIONS = ["read-only", "write"]
TRUSTS = ["owner", "derived", "external"]
SENSITIVITIES = ["private", "generic", "public"]
_MACHINE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _one_line(s: str, limit: int) -> str:
    s = "".join(ch if ch.isprintable() or ch.isspace() else " " for ch in str(s))
    s = " ".join(s.split()).replace('"', "'").replace("\\", "/")
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _flat(s: Any, limit: int = 400) -> str:
    """One line for body text: whitespace and newlines collapsed, nothing else changed (shell quotes survive)."""
    s = "".join(ch if ch.isprintable() or ch.isspace() else " " for ch in str(s))
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _q(s: str) -> str:
    return '"%s"' % s


def build_task(rec: Dict[str, Any], kind: Kind, step: Dict[str, Any]) -> Tuple[str, str]:
    if step.get("template") != "question" or kind.name != "question":
        raise ValueError("no handoff template %r for kind %s" % (step.get("template"), kind.name))
    f, id = rec["fields"], rec["id"]
    trust = f.get("trust") if f.get("trust") in TRUSTS else "external"            # unknown values fail closed
    sens = f.get("sensitivity") if f.get("sensitivity") in SENSITIVITIES else "private"
    machine = f.get("machine") or "any"
    if not _MACHINE_RE.match(machine):
        raise ValueError("machine: %r is not a plain machine name" % (machine,))
    if f.get("due") and not _DATE_RE.match(str(f["due"])):
        raise ValueError("due: %r is not a date like 2026-10-27" % (f["due"],))
    writes = bool(f.get("writes"))
    approval = "before-run" if (writes or trust != "owner") else "none"
    exact = bool(f.get("procedure"))
    tags = ["assembly", "as:" + id, "as-v%d" % HANDOFF_VERSION, "as-exec:" + ("exact" if exact else "agent"),
            "as-trust:" + trust, "as-sens:" + sens]
    head = ["---", "mach: 1", "type: task",
            "title: " + _q(_one_line("%s %s" % (id, f["text"]), 70)),
            "goal: " + _q(_one_line("Answer question %s: %s" % (id, f["text"]), 220)),
            "tool: auto", "output: stdout",
            "permission: " + ("write" if writes else "read-only"),
            "approval: " + approval,
            "machine: " + machine]
    if f.get("path"):
        head.append("path: " + _q(_one_line(f["path"], 200)))
    if f.get("due"):
        head.append("due: " + str(f["due"]))
    head += ["tags: [%s]" % ", ".join(tags), "---"]

    ctx = ["- Assembly ID: %s (handoff v%d)" % (id, HANDOFF_VERSION),
           "- lens: %s; sensitivity: %s; trust: %s" % (_flat(f.get("lens"), 40), sens, trust)]
    for key in ("region", "horizon", "cadence", "bay", "store", "goal", "service"):
        if f.get(key):
            ctx.append("- %s: %s" % (key, _flat(f[key], 160)))
    body = ["", "## Question %s" % id, ""] + ["> " + ln for ln in str(f["text"]).splitlines() or [""]] + ["", "## Context", ""] + ctx + ["", "## Do", ""]
    if exact:
        body.append("Run exactly these steps, in order, and nothing else. If a step fails, stop and report the failure.")
        body.append("")
        body += ["%d. %s" % (i, _flat(st)) for i, st in enumerate(f["procedure"], 1)]
    else:
        body.append("Answer the question using the context above. This task needs an agent: choose the approach, "
                    "stay inside the stated permission, and report findings as a short digest.")
    checks = f.get("checks") or []
    body += ["", "## Done when", "",
             ("- these checks pass: %s" % ", ".join(_flat(c, 80) for c in checks)) if checks else "- the owner confirms the digest",
             "- the reply names the Assembly ID `%s` and what was found" % id, ""]
    name = "%s-as-%s-%s.md" % (rec["created"][:10].replace("-", ""), id.lower(), step["id"])
    return name, "\n".join(head + body)


def check_task(md: str) -> List[str]:
    """Errors against the machine-flows v0 prompt-document key set; empty list means acceptable."""
    try:
        fm = parse_frontmatter(md, strict=True)
    except ValueError as e:
        return ["frontmatter: %s" % e]
    errs = []
    for k in REQUIRED:
        if k not in fm:
            errs.append("%s: required" % k)
    for k in fm:
        if k not in REQUIRED + OPTIONAL:
            errs.append("%s: unknown key" % k)
    if fm.get("mach") != "1":
        errs.append("mach: must be 1")
    if fm.get("type") != "task":
        errs.append("type: must be task")
    for key, allowed in (("tool", TOOLS), ("approval", APPROVALS), ("permission", PERMISSIONS)):
        if key in fm and fm[key] not in allowed:
            errs.append("%s: %r is not one of %s" % (key, fm[key], ", ".join(allowed)))
    tags = fm.get("tags", []) if isinstance(fm.get("tags", []), list) else []
    trust = next((t.split(":", 1)[1] for t in tags if t.startswith("as-trust:")), None)
    if trust not in TRUSTS:
        errs.append("tags: a valid as-trust:<owner|derived|external> tag is required")
    elif trust != "owner" and fm.get("approval") != "before-run":
        errs.append("approval: must be before-run when trust is %s" % trust)
    if fm.get("permission") == "write" and fm.get("approval") != "before-run":
        errs.append("approval: must be before-run when permission is write")
    return errs


def emit(md: str, filename: str, outbox: Path) -> Path:
    outbox = Path(outbox)
    outbox.mkdir(parents=True, exist_ok=True)
    p = outbox / filename
    if p.exists():
        if p.read_text(encoding="utf-8") == md:
            return p
        raise FileExistsError("%s exists with different content; refusing to overwrite" % p)
    tmp = p.with_name("." + p.name + ".tmp")
    tmp.write_text(md, encoding="utf-8")
    os.replace(str(tmp), str(p))
    return p


def emit_for_step(root: Path, rec: Dict[str, Any], kind: Kind, step: Dict[str, Any], outbox: Path) -> Path:
    name, md = build_task(rec, kind, step)
    errs = check_task(md)
    if errs:
        raise ValueError("handoff document failed the v0 check: " + "; ".join(errs))
    return emit(md, name, outbox)
