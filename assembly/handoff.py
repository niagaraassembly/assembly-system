"""Handoff to machine-flows, version 0.

Writes a machine-flows prompt document using only the v0 key set that `mach run` accepts. The body is
deterministic: when the record has a `procedure`, the document says to run exactly those steps and nothing
else, so no interpretation is needed; otherwise it is marked as needing an agent. The link back to the
record and the handoff version travel in `tags` (as:<ID>, as-v0). Later versions replace the tags with
first-class contract keys (machine-flows NA-330).
"""
import os
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


def _one_line(s: str, limit: int) -> str:
    s = "".join(ch if ch.isprintable() or ch.isspace() else " " for ch in str(s))
    s = " ".join(s.split()).replace('"', "'").replace("\\", "/")
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def _q(s: str) -> str:
    return '"%s"' % s


def build_task(rec: Dict[str, Any], kind: Kind, step: Dict[str, Any]) -> Tuple[str, str]:
    if step.get("template") != "question" or kind.name != "question":
        raise ValueError("no handoff template %r for kind %s" % (step.get("template"), kind.name))
    f, id = rec["fields"], rec["id"]
    trust = f.get("trust", "external")
    writes = bool(f.get("writes"))
    approval = "before-run" if (writes or trust != "owner") else "none"
    exact = bool(f.get("procedure"))
    tags = ["assembly", "as:" + id, "as-v%d" % HANDOFF_VERSION, "as-exec:" + ("exact" if exact else "agent"),
            "as-trust:" + trust, "as-sens:" + f.get("sensitivity", "private")]
    head = ["---", "mach: 1", "type: task",
            "title: " + _q(_one_line("%s %s" % (id, f["text"]), 70)),
            "goal: " + _q(_one_line("Answer question %s: %s" % (id, f["text"]), 220)),
            "tool: auto", "output: stdout",
            "permission: " + ("write" if writes else "read-only"),
            "approval: " + approval,
            "machine: " + (f.get("machine") or "any")]
    if f.get("path"):
        head.append("path: " + _q(_one_line(f["path"], 200)))
    if f.get("due"):
        head.append("due: " + f["due"])
    head += ["tags: [%s]" % ", ".join(tags), "---"]

    ctx = ["- Assembly ID: %s (handoff v%d)" % (id, HANDOFF_VERSION),
           "- lens: %s; sensitivity: %s; trust: %s" % (f.get("lens"), f.get("sensitivity"), trust)]
    for key in ("region", "horizon", "cadence", "bay", "store", "goal", "service"):
        if f.get(key):
            ctx.append("- %s: %s" % (key, f[key]))
    body = ["", "## Question %s" % id, ""] + ["> " + ln for ln in str(f["text"]).splitlines() or [""]] + ["", "## Context", ""] + ctx + ["", "## Do", ""]
    if exact:
        body.append("Run exactly these steps, in order, and nothing else. If a step fails, stop and report the failure.")
        body.append("")
        body += ["%d. %s" % (i, s) for i, s in enumerate(f["procedure"], 1)]
    else:
        body.append("Answer the question using the context above. This task needs an agent: choose the approach, "
                    "stay inside the stated permission, and report findings as a short digest.")
    checks = f.get("checks") or []
    body += ["", "## Done when", "",
             ("- these checks pass: %s" % ", ".join(checks)) if checks else "- the owner confirms the digest",
             "- the reply names the Assembly ID `%s` and what was found" % id, ""]
    name = "%s-as-%s-%s.md" % (rec["created"][:10].replace("-", ""), id.lower(), step["id"])
    return name, "\n".join(head + body)


def check_task(md: str) -> List[str]:
    """Errors against the machine-flows v0 prompt-document key set; empty list means acceptable."""
    try:
        fm = parse_frontmatter(md)
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
