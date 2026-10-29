#!/usr/bin/env python3
"""Provenance and discipline checks for a synthetic-research study folder.

Usage: python3 scripts/check_study.py studies/<study>
Exit 0 when there are no errors (warnings allowed), 1 otherwise.

Errors
  - a run transcript without `synthetic: true`, a persona id, or the SYNTHETIC banner
  - a synthesis missing a required section
  - a quoted block without a [SYN: runs/...] or [REAL: E#] tag, or a tag pointing at nothing
  - a [REAL: E#] tag that cites synthetic evidence
  - a hypothesis without a [support: N runs / M personas] tag
  - a persona in the runs with no `Calibration: <persona>: <status>` line, or one that
    does not match calibration/<persona>/STATUS.md (status goes `stale` if the persona file changed)
Warnings
  - single-run hypotheses, overclaiming phrases, leftover TODOs, missing skeptic review
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ["Hypotheses", "Single-persona observations", "Validate with real people", "Limits"]
OVERCLAIM = re.compile(
    r"\b(participants (said|reported|told|agreed)|users (said|reported)|respondents|"
    r"research (shows|found|proves|confirms)|our research|findings? (show|indicate|confirm))\b", re.I)
SUPPORT = re.compile(r"\[support:\s*(\d+)\s*runs?\s*/\s*(\d+)\s*personas?\s*\]", re.I)
SYN = re.compile(r"\[SYN:\s*([^\]\s]+)\s*\]")
REAL = re.compile(r"\[REAL:\s*(E\w+)\s*\]")
CAL = re.compile(r"^Calibration:\s*([\w-]+):\s*([\w-]+)", re.M | re.I)


def frontmatter(text: str):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, m.group(2)


def persona_hash(pid: str):
    for f in (ROOT / "personas").glob("*.md"):
        meta, _ = frontmatter(f.read_text(encoding="utf-8"))
        if (meta.get("id") or f.stem) == pid:
            return hashlib.sha256(f.read_bytes()).hexdigest()[:12]
    return None


def calibration_status(pid: str) -> str:
    f = ROOT / "calibration" / pid / "STATUS.md"
    if not f.exists():
        return "uncalibrated"
    meta, _ = frontmatter(f.read_text(encoding="utf-8"))
    status = meta.get("status", "uncalibrated").lower()
    current = persona_hash(pid)
    if status != "uncalibrated" and current and meta.get("persona_sha256") != current:
        return "stale"
    return status


def load_evidence() -> dict:
    f = ROOT / "evidence" / "evidence.json"
    if not f.exists():
        return {}
    out = {}
    for k, v in json.loads(f.read_text(encoding="utf-8")).items():
        if not k.startswith("_"):
            out[k] = bool(v.get("synthetic")) if isinstance(v, dict) else False
    return out


def section(text: str, name: str) -> str:
    m = re.search(rf"^##\s+{re.escape(name)}.*?$(.*?)(?=^##\s|\Z)", text, re.M | re.S | re.I)
    return m.group(1) if m else ""


def check(study: Path):
    errors, warnings = [], []
    err, warn = errors.append, warnings.append

    personas = set()
    runs = sorted((study / "runs").glob("*.md")) if (study / "runs").is_dir() else []
    if not runs:
        warn("runs/: no transcripts yet")
    for f in runs:
        meta, body = frontmatter(f.read_text(encoding="utf-8"))
        if meta.get("synthetic", "").lower() != "true":
            err(f"runs/{f.name}: frontmatter must contain 'synthetic: true'")
        if not meta.get("persona"):
            err(f"runs/{f.name}: frontmatter must name the persona")
        else:
            personas.add(meta["persona"])
        if not meta.get("run"):
            err(f"runs/{f.name}: frontmatter must contain 'run: <n>'")
        if "SYNTHETIC" not in body[:400]:
            err(f"runs/{f.name}: missing the SYNTHETIC TRANSCRIPT banner")

    syn = study / "synthesis.md"
    if not syn.exists():
        warn("synthesis.md: not written yet")
    else:
        text = syn.read_text(encoding="utf-8")
        lines = text.splitlines()
        heads = [h.strip().lower() for h in re.findall(r"^##\s+(.+?)\s*$", text, re.M)]
        for h in REQUIRED:
            if not any(x.startswith(h.lower()) for x in heads):
                err(f"synthesis.md: missing section '## {h}'")

        # blockquotes: each contiguous block needs a provenance tag
        evidence = load_evidence()
        i = 0
        while i < len(lines):
            if lines[i].lstrip().startswith(">"):
                start = i
                while i < len(lines) and lines[i].lstrip().startswith(">"):
                    i += 1
                block = "\n".join(lines[start:i])
                syn_tags, real_tags = SYN.findall(block), REAL.findall(block)
                if not (syn_tags or real_tags):
                    err(f"synthesis.md:{start + 1}: quoted text without a [SYN: ...] or [REAL: ...] tag")
                for t in syn_tags:
                    if not (study / t).is_file():
                        err(f"synthesis.md:{start + 1}: [SYN: {t}] does not point at a file in this study")
                for t in real_tags:
                    if t not in evidence:
                        err(f"synthesis.md:{start + 1}: [REAL: {t}] is not in evidence/evidence.json")
                    elif evidence[t]:
                        err(f"synthesis.md:{start + 1}: [REAL: {t}] is marked synthetic in the evidence file")
            else:
                i += 1

        # hypotheses need support tags
        for raw in section(text, "Hypotheses").splitlines():
            if re.match(r"^\s*(-|\*|\d+\.)\s+\S", raw):
                m = SUPPORT.search(raw)
                if not m:
                    err(f"synthesis.md: hypothesis lacks a [support: N runs / M personas] tag: {raw.strip()[:70]}")
                elif int(m.group(1)) < 2:
                    warn(f"synthesis.md: single-run hypothesis: {raw.strip()[:70]}")

        # calibration disclosure
        declared = {p.lower(): s.lower() for p, s in CAL.findall(text)}
        for p in sorted(personas):
            actual = calibration_status(p)
            if p.lower() not in declared:
                err(f"synthesis.md: no 'Calibration: {p}: <status>' line (actual status: {actual})")
            elif declared[p.lower()] != actual:
                err(f"synthesis.md: 'Calibration: {p}: {declared[p.lower()]}' does not match actual status '{actual}'")

        for n, line in enumerate(lines, 1):
            if OVERCLAIM.search(line):
                warn(f"synthesis.md:{n}: reads like real-research language: {line.strip()[:70]}")
            if "TODO" in line:
                warn(f"synthesis.md:{n}: leftover TODO")
        if not (study / "skeptic-review.md").exists():
            warn("skeptic-review.md: no skeptic review yet")
    return errors, warnings


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    study = Path(argv[1])
    if not study.is_dir():
        study = ROOT / argv[1]
    if not study.is_dir():
        print(f"not a folder: {argv[1]}")
        return 2
    errors, warnings = check(study)
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"\n{study.name}: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
