"""Persona and evidence file formats, plus static linting.

Persona file (markdown):

    ---
    id: dana
    name: Dana R.
    role: Charge nurse, med-surg
    ---
    ## Profile
    Free text summary.

    ## Claims
    - [E1, E3] behavior: One claim per line, citing evidence ids.
    - [] goal: A claim with no evidence (will be flagged as ungrounded).

Evidence file (JSON): {"E1": {"quote": "...", "source": "int_01", "synthetic": false}, ...}
A bare string value is accepted as shorthand for a real quote.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

CATEGORIES = {"behavior", "workaround", "constraint", "distrust", "goal", "context"}
BEHAVIORAL = CATEGORIES - {"context"}
CLAIM_RE = re.compile(r"^\s*-\s*\[([^\]]*)\]\s*(.+?)\s*$")


@dataclass
class Claim:
    text: str
    evidence: list

    @property
    def category(self):
        m = re.match(r"([a-z]+):\s", self.text, re.I)
        return m.group(1).lower() if m and m.group(1).lower() in CATEGORIES else None


@dataclass
class Persona:
    id: str
    name: str
    role: str
    profile: str
    claims: list
    path: str


def load_persona(path) -> Persona:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    meta, body = {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    section, profile, claims = None, [], []
    for line in body.splitlines():
        h = re.match(r"^##\s+(.*)", line)
        if h:
            section = h.group(1).strip().lower()
            continue
        if section == "profile":
            profile.append(line)
        elif section == "claims":
            cm = CLAIM_RE.match(line)
            if cm:
                ids = [x for x in re.split(r"[,\s]+", cm.group(1)) if x]
                claims.append(Claim(cm.group(2), ids))
    pid = meta.get("id") or path.stem
    return Persona(pid, meta.get("name", pid), meta.get("role", ""), "\n".join(profile).strip(), claims, str(path))


def load_personas_dir(path, exclude_id=None) -> list:
    out = []
    for f in sorted(Path(path).glob("*.md")):
        p = load_persona(f)
        if p.claims and p.id != exclude_id:
            out.append(p)
    return out


def load_evidence(path) -> dict:
    if not path:
        return {}
    out = {}
    for k, v in json.loads(Path(path).read_text(encoding="utf-8")).items():
        if k.startswith("_"):
            continue
        if isinstance(v, str):
            out[k] = {"quote": v, "source": "", "synthetic": False}
        else:
            out[k] = {"quote": v.get("quote", ""), "source": v.get("source", ""), "synthetic": bool(v.get("synthetic", False))}
    return out


def lint(persona: Persona, evidence: dict) -> dict:
    issues = []

    def add(level, code, message, claim=None):
        issues.append({"level": level, "code": code, "message": message, "claim": claim})

    n = len(persona.claims)
    if n == 0:
        add("error", "NO_CLAIMS", "Persona file has no claims under '## Claims'.")
    grounded = thick = 0
    for c in persona.claims:
        valid = [e for e in c.evidence if e in evidence]
        missing = [e for e in c.evidence if e not in evidence]
        synthetic = [e for e in valid if evidence[e]["synthetic"]]
        real = [e for e in valid if not evidence[e]["synthetic"]]
        if missing:
            add("error", "MISSING_EVIDENCE", f"Cites evidence id(s) not in the evidence file: {', '.join(missing)}", c.text)
        if synthetic:
            add("error", "SYNTHETIC_EVIDENCE", f"Grounded on synthetic output ({', '.join(synthetic)}). That is circular.", c.text)
        if not c.evidence:
            add("warn", "UNGROUNDED", "No evidence cited. Treat as the model's inference, not a finding.", c.text)
        elif len(real) == 1:
            add("info", "THIN", "Only one real evidence item supports this claim.", c.text)
        grounded += bool(real)
        thick += len(real) >= 2
    behavioral = sum(1 for c in persona.claims if c.category in BEHAVIORAL)
    if n and behavioral < 3:
        add("warn", "DEMOGRAPHIC_ONLY", f"Only {behavioral} behavioral claim(s) (behavior/workaround/constraint/distrust/goal). "
                                        "Personas without a behavior model produce generic answers.")
    return {
        "issues": issues,
        "n_claims": n,
        "grounded": grounded / n if n else 0.0,
        "thick": thick / n if n else 0.0,
        "errors": sum(i["level"] == "error" for i in issues),
    }
