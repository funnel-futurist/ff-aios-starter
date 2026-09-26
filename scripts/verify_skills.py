#!/usr/bin/env python3
"""verify_skills.py — structural skill contract enforcement.

A skill is a promise that a job will be done the same way every time. Three things
make that promise keepable, and all three are checkable by a machine:

  REFERENCES      — the skill names the specific files it must obey, AND THOSE
                    FILES EXIST. A skill pointing at a deleted doc fails silently:
                    the model improvises and nobody finds out until the output is wrong.
  SPECIFICITY     — the description says what this skill is NOT for, and the body
                    says which skill to use instead. Claude Code dispatches on the
                    description, so a vague description is a routing bug.
  REPRODUCIBILITY — a definition of done, a checklist, and evidence per item.
                    Without those, "done" is whatever the model felt like this time.

This is a bounded structural guard. It checks structure and file existence,
not content quality or IP classification.

Exit code is 0 unless --strict, so this is safe in CI as a report first.

  python3 scripts/verify_skills.py                 # scorecard
  python3 scripts/verify_skills.py --skill x       # one skill, verbose
  python3 scripts/verify_skills.py --broken-refs   # only the dead references
  python3 scripts/verify_skills.py --checklists    # paired-checklist work-list
  python3 scripts/verify_skills.py --resources     # every Resource: link + dead ones
  python3 scripts/verify_skills.py --strict        # exit 1 on dead references
  python3 scripts/verify_skills.py --strict-checklists  # exit 1 on checklist failures
  python3 scripts/verify_skills.py --json
"""
from __future__ import annotations
import argparse
import json
import pathlib
import re
import subprocess
import sys

# ── Portable repo detection ──────────────────────────────────────────────────
def _find_repo_root():
    """Find the repo root via git, falling back to the script's grandparent."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0 and out.stdout.strip():
            return pathlib.Path(out.stdout.strip())
    except Exception:
        pass
    # Fallback: script is at REPO/scripts/verify_skills.py
    return pathlib.Path(__file__).resolve().parent.parent


REPO = pathlib.Path(__file__).resolve().parent.parent
SKILLS = REPO / ".claude/skills"

# A token only counts as a reference if it looks like a repo path, not like `out.mp4`.
PATH_RE = re.compile(r"`([^`\n]{4,200}?\.(?:md|py|js|jsx|ts|tsx|sql|ya?ml|json|txt|html|css))`")
# Hints that a backtick-wrapped path is a REPO reference, not an output target.
ROOT_HINTS = (".claude/", "scripts/", "docs/",
              "01_", "02_", "03_", "04_", "05_", "06_", "07_", "08_", "09_",
              "10_", "11_", "12_", "13_", "14_")

NOT_RE = re.compile(r"\bNOT\b|\bnot for\b|\binstead\b|\bdoes not\b|\brather than\b", re.I)


def frontmatter(text):
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fm, out = text[3:end], {}
    for key in ("name", "description"):
        m = re.search(rf"^{key}:\s*(.+?)(?=\n\w+:|\Z)", fm, re.S | re.M)
        if m:
            out[key] = m.group(1).strip().strip('"').strip("'")
    return out


_BASENAME_INDEX = None


def _basename_index():
    """Basenames across the repo so we can tell UNANCHORED from DEAD."""
    global _BASENAME_INDEX
    if _BASENAME_INDEX is None:
        idx = {}
        if REPO.exists():
            for f in REPO.rglob("*"):
                if f.is_file() and "/node_modules/" not in str(f) and "/.git/" not in str(f):
                    idx.setdefault(f.name, []).append(f)
        _BASENAME_INDEX = idx
    return _BASENAME_INDEX


def resolve(p: str, skill_dir: pathlib.Path = None):
    """Returns 'ok' | 'unanchored' | 'dead' | None (not checkable).

    A skill points at its own reference files RELATIVELY (references/<name>.md),
    and that is the most common kind of reference. Resolve against the skill's
    own directory FIRST.

    UNANCHORED = a bare filename with no directory. The model has to hunt for it,
    and it silently binds to the wrong file the day a second copy appears.
    """
    p = p.strip()
    if p.startswith("http"):
        return None
    cand = pathlib.Path(p)
    if cand.is_absolute():
        return "dead"
    roots = [skill_dir, REPO] if skill_dir else [REPO]
    if not any((root / p).resolve().is_relative_to(REPO.resolve()) for root in roots):
        return "dead"
    if "{" in p or "*" in p:
        return "dead"  # Public references must be concrete and verifiable.
    if skill_dir is not None and (skill_dir / p).resolve().is_relative_to(REPO.resolve()) and (skill_dir / p).exists():
        return "ok"
    if (REPO / p).resolve().is_relative_to(REPO.resolve()) and (REPO / p).exists():
        return "ok"
    return "unanchored" if _basename_index().get(cand.name) else "dead"


# ── Checklist clause — every item carries an Example AND a Counter-example ───
# The heading vocabulary for definition-of-done / QC sections:
CL_SECTION_RE = re.compile(
    r"(?im)^(#{2,4})\s*(.*?(?:definition of done|done when|\bdod\b|\bqc\b|qc[- ]?(?:gate|chain|"
    r"checklist|dimension)|quality (?:bar|gate|gates|checklist|control)|checklist).*)$")

# An ITEM is a thing a reader ticks. Five shapes exist:
CL_ITEM_RE = re.compile(r"""(?x)
      ^\s*[-*]\s\[[ xX]\]                      # - [ ] task item
    | ^\s*\#{2,5}\s*[A-Z]{1,4}-\d+\b           # ### C-3 - SPEC item format
    | ^\s*\#{3,5}\s*(?:Step|Gate|Check)\s+\d+  # ### Step 3 - run-step format
    | ^\s*\|\s*\*{0,2}(?:[A-Z]{1,4}-)?\d+\*{0,2}\s*\|   # | 3 | or | C-3 | table row
    | ^\s*\d{1,2}[.)]\s+\S                     # 1. numbered item
""")

# Strict shape for pointed-at files (no bare `1.` numbering):
CL_ITEM_STRICT_RE = re.compile(r"""(?x)
      ^\s*[-*]\s\[[ xX]\]
    | ^\s*\#{2,5}\s*[A-Z]{1,4}-\d+\b
    | ^\s*\#{3,5}\s*(?:Step|Gate|Check)\s+\d+
    | ^\s*\|\s*\*{0,2}(?:[A-Z]{1,4}-)?\d+\*{0,2}\s*\|
""")

# Three dialects for pass/fail pairs:
CL_EX_MARK = re.compile(r"✅|✔|(?<!\S)✓")
CL_CTR_MARK = re.compile(r"❌|✘|(?<!\S)✗")
CL_EX_WORD = re.compile(r"(?i)\bexamples?\s*[:—-]|\*\*examples?\b|\bpasses\s*:|\bgood\s*:")
CL_CTR_WORD = re.compile(r"(?i)«CTR»|\bnear[-\s]miss\b|\bfails\s*:|\bbad\s*:|\banti[-\s]example\b")

# LABEL introduces a half (boundary). WEAK satisfies without bounding.
CL_EX_WORD_LABEL = re.compile(r"(?i)\bexamples?\s*[:—-]|\*\*examples?\b|\bpasses\s*:|\bgood\s*:")
CL_CTR_WORD_LABEL = re.compile(r"(?i)«CTR»|(?<!why it )(?<!why this )\bfails\s*:|\bbad\s*:")
CL_CTR_WEAK = re.compile(r"(?i)\bnear[-\s]miss\b|\banti[-\s]example\b")
CL_PRODUCE = re.compile(r"(?i)\bPRODUCE\s*:")
CL_WRONG_IF = re.compile(r"(?i)\bWRONG IF\s*:")

# Resource: field — the link the operator opens to do the work.
# Accepts plain, bold-wrapped, and backtick-wrapped dialects.
RESOURCE_FIELD_RE = re.compile(r"(?im)^\s*[-*]?\s*[`*]{0,2}Resource[`*]{0,2}\s*:\s*[`*]{0,2}\s*")
FIELD_START_RE = re.compile(r"^\s*[-*]\s*\*{2}")
# Capture paths from Resource: fields, handling braces and brackets.
RES_PATH_RE = re.compile(
    r"`?((?:(?:[\w.\-{}\[\]]+|\*)/)*[\w.\-{}\[\]]{3,120}"
    r"\.(?:jsonl|json|jsx|js|tsx|ts|yaml|yml|html|css|md|py|sql|txt|csv))`?")

# An item naming a swipe/template/golden/lock file needs a Resource: link.
RESOURCE_TRIGGER_RE = re.compile(
    r"(?i)\b(swipes?|swipe ?file|swipefile|templates?|golden|gold standard|lock ?file|"
    r"corpus|index|library|taxonomy|register|reference image)\b")

# Pointer to an external paired-checklist file.
CL_POINTER_RE = re.compile(r"(?i)<!--\s*CHECKLIST\s*:\s*path\s*=\s*([^\s;>]+)")
CL_POINTER_LINE_RE = re.compile(r"(?im)^\s*checklist\s*:\s*`?([\w./\-]+\.(?:md|markdown))`?\s*$")

# GATHER block — numbered items with G-n IDs.
CL_GATHER_ITEM_RE = re.compile(r"(?m)^\s*#{2,5}\s*G-\d+\b")
GATHER_HEAD_RE = re.compile(r"(?im)^#{1,5}\s*.*\bgather\b.*$")

# A PRODUCING skill makes an artifact, so it needs a GATHER block.
PRODUCER_NAME_RE = re.compile(
    r"(?:^|[_-])(build|builder|write|writer|writing|draft|create|creator|generate|generator|"
    r"generation|produce|producer|production|design|designer|forge|architect|copywriter|make|"
    r"compose|pack|script|scripts|scaffold)(?:[_-]|$)")
GATE_NAME_RE = re.compile(
    r"(?:^|[_-])(qc|gate|verifier|verify|grader|grade|scan|review|reviewer|audit|auditor|check|"
    r"lint|evaluator|spot_check)(?:[_-]|$)")

# ── Content substantiveness ──────────────────────────────────────────────────
CL_MIN_HALF_CHARS = 4
CL_THIN_HALF_CHARS = 25

CL_VERDICT_WORD_RE = re.compile(
    r"(?i)^(?:good|bad|yes|no|nope|pass(?:es|ed)?|fail(?:s|ed)?|ok|okay|fine|correct|wrong|right|"
    r"true|false|n/?a|none|clean|dirty|done)$")
CL_MEASURED_RE = re.compile(
    r"(?i)^[<>=~+-]{0,2}\s*\d[\d.,:/]*\s*(?:%|[a-z]{1,12}(?:\s+[a-z]{1,12}){0,2})?$")

CL_MARKERS = (("ex", CL_EX_MARK), ("ex", CL_EX_WORD_LABEL), ("ex", CL_PRODUCE),
              ("ctr", CL_CTR_MARK), ("ctr", CL_CTR_WORD_LABEL), ("ctr", CL_WRONG_IF))
CL_LABEL_ANY = re.compile("|".join(rx.pattern.replace("(?i)", "") for _, rx in CL_MARKERS),
                          re.IGNORECASE)


# ── Section / item parsing ───────────────────────────────────────────────────

def _span(body, pos, lvl, all_heads):
    """Where a heading's section ends: next heading at same level or shallower."""
    for hpos, hlvl in all_heads:
        if hpos > pos and hlvl <= lvl:
            return hpos
    return len(body)


def _cl_sections(body):
    """Every definition-of-done / QC / checklist / GATHER section."""
    all_heads = [(m.start(), len(m.group(1))) for m in re.finditer(r"(?m)^(#{1,6})\s", body)]
    out = []
    for m in CL_SECTION_RE.finditer(body):
        pos, lvl, title = m.start(), len(m.group(1)), m.group(2).strip()
        end = _span(body, pos, lvl, all_heads)
        if any(s <= pos < e for _, _, s, e in out):
            continue
        out.append((title, body[pos:end], pos, end))
    return out


def _cl_items(section_text, strict_ids=False):
    """Split a section into item blocks."""
    rx = CL_ITEM_STRICT_RE if strict_ids else CL_ITEM_RE
    lines = section_text.split("\n")
    starts = [i for i, ln in enumerate(lines) if rx.match(ln)]
    blocks = []
    for n, i in enumerate(starts):
        j = starts[n + 1] if n + 1 < len(starts) else len(lines)
        blocks.append("\n".join(lines[i:j]))
    return blocks


def _resource_field(block):
    """The Resource: field of an item block, including wrapped continuation lines."""
    lines = block.split("\n")
    out = []
    for i, ln in enumerate(lines):
        if not RESOURCE_FIELD_RE.match(ln):
            continue
        buf = [ln]
        for nxt in lines[i + 1:]:
            if FIELD_START_RE.match(nxt) or CL_ITEM_RE.match(nxt) or nxt.startswith("#") \
                    or not nxt.strip():
                break
            buf.append(nxt)
        out.append("\n".join(buf))
    return out


def _strip_resource_fields(block):
    """Remove Resource fields before pair detection to avoid false positives from paths."""
    text = block
    for f in _resource_field(block):
        text = text.replace(f, " ")
    return text


def _half_content(nc, start, stop):
    """The content of one half: from the end of its marker to the next marker, trimmed."""
    seg = nc[start:stop]
    lines = seg.split("\n")
    keep = [lines[0]]
    for nxt in lines[1:]:
        if FIELD_START_RE.match(nxt) or CL_ITEM_RE.match(nxt) or nxt.startswith("#") \
                or not nxt.strip():
            break
        keep.append(nxt)
    txt = re.sub(r"\s+", " ", "\n".join(keep)).strip()
    txt = CL_LABEL_ANY.sub(" ", txt)
    return txt.strip("*:—-·`\"'|> ").strip()


def _half_is_substantive(txt):
    """Does this half carry evidence? A measurement does. A verdict word does not."""
    if not txt:
        return False
    if CL_MEASURED_RE.match(txt):
        return True
    if CL_VERDICT_WORD_RE.match(txt):
        return False
    return len(re.sub(r"\s+", "", txt)) >= CL_MIN_HALF_CHARS


def _cl_marks(nc):
    """Every marker in the block as (start, end_of_marker, side), in document order."""
    return sorted((m.start(), m.end(), side)
                  for side, rx in CL_MARKERS for m in rx.finditer(nc))


def _cl_halves(nc):
    """{side: [content, ...]} sorted substantive-first."""
    marks = _cl_marks(nc)
    out = {"ex": [], "ctr": []}
    for n, (st, e, side) in enumerate(marks):
        stop = marks[n + 1][0] if n + 1 < len(marks) else len(nc)
        out[side].append(_half_content(nc, e, stop))
    return {k: sorted(v, key=lambda t: (_half_is_substantive(t), len(t)), reverse=True)
            for k, v in out.items()}


def _cl_pair(block):
    """Does this item block carry BOTH halves, each with CONTENT? Returns dialect or None."""
    nc = re.sub(r"(?i)counter[-\s]?examples?", "«CTR»", _strip_resource_fields(block))
    marks = _cl_marks(nc)

    def substantive(rx, side):
        for n, (st, e, sd) in enumerate(marks):
            if sd != side or not rx.match(nc, st):
                continue
            stop = marks[n + 1][0] if n + 1 < len(marks) else len(nc)
            if _half_is_substantive(_half_content(nc, e, stop)):
                return True
        return False

    if substantive(CL_EX_WORD_LABEL, "ex") and (substantive(CL_CTR_WORD_LABEL, "ctr")
                                                or CL_CTR_WEAK.search(nc)):
        return "labelled"
    if substantive(CL_PRODUCE, "ex") and substantive(CL_WRONG_IF, "ctr"):
        return "produce/wrong-if"
    halves = _cl_halves(nc)
    ex = bool(halves["ex"]) and _half_is_substantive(halves["ex"][0])
    ctr = (bool(halves["ctr"]) and _half_is_substantive(halves["ctr"][0])) \
        or bool(CL_CTR_WEAK.search(nc))
    if ex and ctr:
        return "marker"
    return None


def _cl_thin(block):
    """Paired, but one half is under the reported-thin floor."""
    nc = re.sub(r"(?i)counter[-\s]?examples?", "«CTR»", _strip_resource_fields(block))
    h = _cl_halves(nc)
    if not h["ex"] or not h["ctr"]:
        return not CL_CTR_WEAK.search(nc) or not h["ex"]
    return min(len(re.sub(r"\s+", "", h["ex"][0])),
               len(re.sub(r"\s+", "", h["ctr"][0]))) < CL_THIN_HALF_CHARS


def _cl_pointers(body):
    """Explicitly declared paired-checklist files."""
    return list(dict.fromkeys(CL_POINTER_RE.findall(body) + CL_POINTER_LINE_RE.findall(body)))


def _item_id(block):
    """The citable ID off the item's first line."""
    head = block.split("\n", 1)[0].strip()
    m = re.search(r"([A-Z]{1,4}-\d+)", head)
    return m.group(1) if m else head.strip("#*-[ ]|").strip()[:44]


def checklist_audit(body, skill_dir: pathlib.Path = None):
    """Explicit, count-reporting audit of the paired-checklist contract.

    Every failure carries a REASON naming what the gate could not find.

    Audits SKILL.md AND every file it points at with <!-- CHECKLIST: path=... -->
    because SKILL.md is the contract and references/ carries the depth.
    """
    a = {"sections": [], "items": 0, "paired": 0, "dialects": [], "reason": "", "pass": False,
         "pointers": [], "pointers_dead": [], "files_audited": [],
         "resources": 0, "resource_paths": [], "resources_dead": [], "resources_unanchored": [],
         "needs_resource": [], "gather": False, "thin": 0}

    texts = [("SKILL.md", body)]
    a["pointers"] = _cl_pointers(body)
    for ptr in a["pointers"]:
        got = None
        if skill_dir is not None and (skill_dir / ptr).resolve().is_relative_to(REPO.resolve()) and (skill_dir / ptr).exists():
            got = skill_dir / ptr
        elif (REPO / ptr).resolve().is_relative_to(REPO.resolve()) and (REPO / ptr).exists():
            got = REPO / ptr
        if got is None:
            a["pointers_dead"].append(ptr)
            continue
        a["files_audited"].append(ptr)
        texts.append((ptr, got.read_text(errors="replace")))

    dialects = set()
    for label, text in texts:
        secs = _cl_sections(text)
        whole_file = not secs and label != "SKILL.md"
        if whole_file:
            secs = [(label, text, 0, len(text))]
        a["sections"] += [f"{t}" if label == "SKILL.md" else f"{label}: {t}"
                          for t, _, _, _ in secs]
        if CL_GATHER_ITEM_RE.search(text):
            a["gather"] = True
        for _, stext, _, _ in secs:
            for blk in _cl_items(stext, strict_ids=whole_file):
                a["items"] += 1
                d = _cl_pair(blk)
                if d:
                    a["paired"] += 1
                    dialects.add(d)
                    if _cl_thin(blk):
                        a["thin"] += 1
                fields = _resource_field(blk)
                a["resources"] += len(fields)
                paths = []
                for f in fields:
                    paths += [m for m in RES_PATH_RE.findall(f)]
                for path in dict.fromkeys(paths):
                    a["resource_paths"].append(path)
                    got = resolve(path, skill_dir)
                    if got == "dead":
                        a["resources_dead"].append(path)
                    elif got == "unanchored":
                        a["resources_unanchored"].append(path)
                if not fields and RESOURCE_TRIGGER_RE.search(blk) and not PATH_RE.search(blk) \
                        and not RES_PATH_RE.search(blk):
                    a["needs_resource"].append(_item_id(blk))
    a["dialects"] = sorted(dialects)
    a["resource_paths"] = list(dict.fromkeys(a["resource_paths"]))

    if a["pointers_dead"]:
        a["reason"] = ("DEAD POINTER: declared checklist file(s) "
                       f"{', '.join(a['pointers_dead'])} do not exist")
        return a
    if not a["sections"]:
        a["reason"] = ("NO SECTION: found no definition-of-done / QC / quality-bar / checklist / "
                       "GATHER heading and no `<!-- CHECKLIST: path=... -->` pointer")
        return a
    if a["items"] == 0:
        a["reason"] = (f"UNPARSEABLE: section(s) {', '.join(a['sections'][:2])!r} exist but 0 "
                       "checklist items parsed")
        return a
    if a["items"] < 3:
        a["reason"] = f"TOO FEW: {a['items']} item(s) parsed; the contract needs at least 3"
        return a
    if a["paired"] < a["items"]:
        a["reason"] = (f"{a['paired']}/{a['items']} items carry an example + counter-example; "
                       f"{a['items'] - a['paired']} missing")
        return a
    if a["resources_dead"]:
        a["reason"] = (f"DEAD RESOURCE: {len(a['resources_dead'])} Resource: link(s) do not "
                       f"resolve: {', '.join(dict.fromkeys(a['resources_dead']))}")
        return a
    a["pass"] = True
    return a


def is_producer(name: str) -> bool:
    """Does this skill PRODUCE an artifact (so it needs a GATHER block)?"""
    return bool(PRODUCER_NAME_RE.search(name)) and not bool(GATE_NAME_RE.search(name))


def check(skill_dir: pathlib.Path):
    """Run all contract checks on a single skill directory."""
    f = skill_dir / "SKILL.md"
    text = f.read_text(errors="replace")
    fm = frontmatter(text)
    body = text
    r = {"skill": skill_dir.name, "bytes": len(text)}

    # SPECIFICITY
    desc = fm.get("description", "")
    r["has_description"] = bool(desc)
    r["name_matches_folder"] = fm.get("name") == skill_dir.name
    r["desc_len"] = len(desc)
    r["desc_has_not_clause"] = bool(NOT_RE.search(desc))
    r["has_boundary_table"] = bool(re.search(
        r"(?im)^#{1,4}\s*(boundar|when not|not this skill|use instead|routing)", body)) or \
        bool(re.search(r"\|\s*(Ask|Input|Request)\s*\|\s*Skill\s*\|", body))
    r["names_sibling_skills"] = len(set(re.findall(r"`([a-z][a-z0-9_]{4,40})`", body))
                                    & {d.name for d in SKILLS.iterdir() if d.is_dir()})

    cl = checklist_audit(body, skill_dir)

    # REFERENCES
    SKILL_LOCAL = re.compile(r"^(references|scripts|assets|templates)/")
    raw = [m for m in PATH_RE.findall(body)
           if any(h in m for h in ROOT_HINTS) or "/" not in m
           or SKILL_LOCAL.match(m)]
    raw += cl["resource_paths"] + cl["pointers"]
    refs, dead, unanchored = [], [], []
    for p in dict.fromkeys(raw):
        got = resolve(p, skill_dir)
        if got is None:
            continue
        refs.append(p)
        if got == "dead":
            dead.append(p)
        elif got == "unanchored":
            unanchored.append(p)
    r["refs_total"] = len(refs)
    r["refs_dead"] = dead
    r["refs_unanchored"] = unanchored
    r["has_refs"] = len(refs) > 0

    # REPRODUCIBILITY
    r["has_definition_of_done"] = bool(re.search(
        r"(?im)^#{1,4}\s*(definition of done|done when|dod\b|output|deliverable)", body)) or \
        bool(re.search(r"(?i)\*\*definition of done", body))
    r["has_checklist"] = (
        body.count("- [ ]") + len(re.findall(r"(?m)^\s*\|\s*\d+\s*\|", body)) > 2
        or cl["items"] > 2
    )
    r["checklist_sections"] = cl["sections"]
    r["checklist_items"] = cl["items"]
    r["checklist_paired"] = cl["paired"]
    r["checklist_thin"] = cl["thin"]
    r["checklist_dialects"] = cl["dialects"]
    r["checklist_reason"] = cl["reason"]
    r["checklist_pointers"] = cl["pointers"]
    r["checklist_pointers_dead"] = cl["pointers_dead"]
    r["checklist_files_audited"] = cl["files_audited"]
    r["resources"] = cl["resources"]
    r["resources_dead"] = cl["resources_dead"]
    r["resources_unanchored"] = cl["resources_unanchored"]
    r["items_needing_a_resource"] = cl["needs_resource"]
    r["has_gather_block"] = cl["gather"]
    r["mentions_gathering"] = bool(GATHER_HEAD_RE.search(body))
    r["is_producer"] = is_producer(skill_dir.name)
    r["is_gate_skill"] = bool(GATE_NAME_RE.search(skill_dir.name))
    r["items_have_examples"] = cl["pass"]

    r["has_gold_standard"] = bool(re.search(
        r"(?i)gold[- ]standard|golden example|golden by path|compare against.*golden", body))
    r["declares_no_gold"] = bool(re.search(
        r"(?i)no (approved )?gold(en)?[- ]standard|no golden yet|has no golden", body))
    r["has_qc_gate"] = bool(re.search(r"(?i)quality_gate|## *QC|QC (gate|dimension|chain)", body))
    r["has_escalation"] = bool(re.search(
        r"(?i)route (it |them )?(back )?to|dispatch|hand it to|use instead", body))

    checks = {
        "name_matches_folder": r["name_matches_folder"],
        "desc_has_not_clause": r["desc_has_not_clause"],
        "has_boundary_table": r["has_boundary_table"],
        "has_refs": r["has_refs"],
        "no_dead_refs": not dead,
        "refs_are_anchored": not unanchored,
        "has_definition_of_done": r["has_definition_of_done"],
        "has_checklist": r["has_checklist"],
        "gold_named_or_declared": r["has_gold_standard"] or r["declares_no_gold"],
        "has_qc_gate": r["has_qc_gate"],
        "has_escalation": r["has_escalation"],
        "items_have_examples": r["items_have_examples"],
    }
    r["checks"] = checks
    r["score"] = sum(checks.values())
    r["max"] = len(checks)
    return r


def main():
    ap = argparse.ArgumentParser(
        description="Structural skill contract enforcement for .claude/skills/")
    ap.add_argument("--skill", help="check a single skill by folder name")
    ap.add_argument("--json", action="store_true", help="output as JSON")
    ap.add_argument("--broken-refs", action="store_true", help="show only dead references")
    ap.add_argument("--min", type=int, default=0, help="only show skills at or below this score")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any checked skill has a dead reference")
    ap.add_argument("--checklists", action="store_true",
                    help="paired-checklist report: per skill, paired/total + reason")
    ap.add_argument("--strict-checklists", action="store_true", dest="strict_checklists",
                    help="exit 1 if any checked skill fails the checklist clause")
    ap.add_argument("--resources", action="store_true",
                    help="every Resource: link found, every DEAD one")
    a = ap.parse_args()

    if not SKILLS.is_dir():
        print(f"no skills directory at {SKILLS}", file=sys.stderr)
        return 1

    dirs = sorted(d for d in SKILLS.iterdir() if d.is_dir() and (d / "SKILL.md").exists())
    if a.skill:
        dirs = [d for d in dirs if d.name == a.skill]
        if not dirs:
            print(f"no such skill: {a.skill}", file=sys.stderr)
            return 1
    rows = [check(d) for d in dirs]

    if a.json:
        print(json.dumps(rows, indent=2))
        return 0

    if a.checklists:
        for r in sorted(rows, key=lambda r: (r["checks"]["items_have_examples"],
                                             -r["checklist_items"])):
            mark = "PASS" if r["checks"]["items_have_examples"] else "FAIL"
            extra = ""
            if r["resources_dead"]:
                extra = f"  DEAD Resource: {len(r['resources_dead'])}"
            elif r["items_needing_a_resource"]:
                extra = (f"  needs Resource: {len(r['items_needing_a_resource'])}"
                         f" ({', '.join(r['items_needing_a_resource'][:3])})")
            print(f"{mark}      {r['skill']:<32} {r['checklist_paired']:>3}/"
                  f"{r['checklist_items']:<3} {r['checklist_reason'][:64]}{extra}")
        n_ok = sum(1 for r in rows if r["checks"]["items_have_examples"])
        print(f"\n  {n_ok}/{len(rows)} passing")
        return 1 if (a.strict_checklists and n_ok < len(rows)) else 0

    if a.resources:
        n_res = n_dead = n_need = 0
        for r in rows:
            if not (r["resources"] or r["items_needing_a_resource"]
                    or r["checklist_pointers"]):
                continue
            print(f"\n{r['skill']}  ({r['resources']} Resource: field(s), "
                  f"{len(r['resources_dead'])} dead)")
            for path in dict.fromkeys(r["resources_dead"]):
                print(f"    DEAD        {path}")
            for path in dict.fromkeys(r["resources_unanchored"]):
                print(f"    unanchored  {path}")
            for path in r["checklist_pointers"]:
                state = "DEAD" if path in r["checklist_pointers_dead"] else "ok  "
                print(f"    pointer {state} {path}")
            for item in r["items_needing_a_resource"]:
                print(f"    NEEDS A LINK  {item}")
            n_res += r["resources"]
            n_dead += len(r["resources_dead"])
            n_need += len(r["items_needing_a_resource"])
        print(f"\n  {n_res} Resource: field(s) across "
              f"{sum(1 for r in rows if r['resources'])} skills | {n_dead} DEAD | "
              f"{n_need} item(s) name a swipe/template/golden with no link")
        return 1 if (a.strict and n_dead) else 0

    if a.broken_refs:
        n = 0
        for r in rows:
            if r["refs_dead"] or r["refs_unanchored"]:
                print(f"\n{r['skill']}  ({len(r['refs_dead'])} dead, "
                      f"{len(r['refs_unanchored'])} unanchored, of {r['refs_total']})")
                for p in r["refs_dead"]:
                    print(f"    DEAD       {p}")
                for p in r["refs_unanchored"]:
                    print(f"    unanchored {p}")
                n += len(r["refs_dead"])
        print(f"\n{n} DEAD across {sum(1 for r in rows if r['refs_dead'])} skills | "
              f"{sum(len(r['refs_unanchored']) for r in rows)} unanchored across "
              f"{sum(1 for r in rows if r['refs_unanchored'])} skills")
        return 1 if (a.strict and n) else 0

    if a.skill:
        r = rows[0]
        print(f"\n{r['skill']}  --  {r['score']}/{r['max']}\n")
        for k, v in r["checks"].items():
            print(f"  {'PASS' if v else 'FAIL'}  {k}")
        print(f"\n  checklist items with example+counter-example: "
              f"{r['checklist_paired']}/{r['checklist_items']}"
              + (f"   dialect(s): {', '.join(r['checklist_dialects'])}"
                 if r['checklist_dialects'] else "   dialect(s): none recognised"))
        print(f"  sections audited: {', '.join(r['checklist_sections']) or 'NONE'}")
        print(f"  files audited: SKILL.md"
              + (", " + ", ".join(r["checklist_files_audited"])
                 if r["checklist_files_audited"] else "")
              + (f"   DEAD POINTER: {', '.join(r['checklist_pointers_dead'])}"
                 if r["checklist_pointers_dead"] else ""))
        print(f"  Resource: links: {r['resources']}   dead: {len(r['resources_dead'])}"
              + (f"   items needing one: {', '.join(r['items_needing_a_resource'])}"
                 if r["items_needing_a_resource"] else ""))
        for path in dict.fromkeys(r["resources_dead"]):
            print(f"    DEAD Resource:  {path}")
        print(f"  GATHER block (G-n items): {'yes' if r['has_gather_block'] else 'NO'}"
              + ("  -- producing skill with no GATHER block"
                 if r["is_producer"] and not r["has_gather_block"] else "")
              + ("  (mentions gathering in prose only)"
                 if r["mentions_gathering"] and not r["has_gather_block"] else ""))
        if r["checklist_reason"]:
            print(f"  items_have_examples FAILED: {r['checklist_reason']}")
        print(f"\n  references found: {r['refs_total']}   dead: {len(r['refs_dead'])}")
        for p in r["refs_dead"]:
            print(f"    DEAD       {p}")
        for p in r.get("refs_unanchored", []):
            print(f"    unanchored {p}")
        if a.strict:
            if r["refs_dead"]:
                return 1
            if a.strict_checklists and not r["checks"]["items_have_examples"]:
                return 1
        return 0

    rows_sorted = sorted(rows, key=lambda r: (r["score"], -len(r["refs_dead"])))
    shown = [r for r in rows_sorted if not a.min or r["score"] <= a.min]
    print(f"{'skill':<34} {'score':>6}  {'refs':>5} {'dead':>5}  missing")
    print("-" * 100)
    for r in shown:
        miss = ",".join(k for k, v in r["checks"].items() if not v)
        print(f"{r['skill']:<34} {r['score']:>3}/{r['max']:<2} {r['refs_total']:>5} "
              f"{len(r['refs_dead']):>5}  {miss[:58]}")

    n = len(rows)
    print(f"\n-- {n} skills --")
    for k in rows[0]["checks"]:
        c = sum(1 for r in rows if r["checks"][k])
        print(f"  {c:>3}/{n}  ({100*c//n:>3}%)  {k}")
    it_tot = sum(r["checklist_items"] for r in rows)
    it_pair = sum(r["checklist_paired"] for r in rows)
    it_thin = sum(r.get("checklist_thin", 0) for r in rows)
    no_sec = [r for r in rows if r["checklist_reason"].startswith("NO SECTION")]
    unparse = [r for r in rows if r["checklist_reason"].startswith("UNPARSEABLE")]
    print(f"\n  CHECKLIST CLAUSE -- items carrying example+counter-example: "
          f"{it_pair}/{it_tot} across {n} skills"
          + (f"  ({100*it_pair//it_tot}%)" if it_tot else "  (0 items parsed)"))
    print(f"    {len(no_sec)} skills have NO definition-of-done/QC section | "
          f"{len(unparse)} have one but 0 parseable items")
    print(f"    {it_thin} paired item(s) carry a THIN half (under {CL_THIN_HALF_CHARS} chars)")

    res_tot = sum(r["resources"] for r in rows)
    res_dead = sum(len(r["resources_dead"]) for r in rows)
    res_need = sum(len(r["items_needing_a_resource"]) for r in rows)
    print(f"\n  RESOURCE LINKS -- {res_tot} field(s) across "
          f"{sum(1 for r in rows if r['resources'])} skills | {res_dead} DEAD")
    print(f"    {res_need} item(s) name a swipe/template/golden with no link")
    prod = [r for r in rows if r["is_producer"]]
    prod_ok = [r for r in prod if r["has_gather_block"]]
    prose_only = [r for r in rows if r["mentions_gathering"] and not r["has_gather_block"]]
    print(f"  GATHER BLOCKS -- {len(prod_ok)}/{len(prod)} producing skills carry one | "
          f"{len(prose_only)} mention gathering in prose only")

    dead_total = sum(len(r["refs_dead"]) for r in rows)
    print(f"\n  {dead_total} DEAD REFERENCES across {sum(1 for r in rows if r['refs_dead'])} skills")
    print(f"  mean score {sum(r['score'] for r in rows)/n:.1f}/{rows[0]['max']}")
    if a.strict and dead_total:
        return 1
    if a.strict_checklists:
        n_ok = sum(1 for r in rows if r["checks"]["items_have_examples"])
        if n_ok < len(rows):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
