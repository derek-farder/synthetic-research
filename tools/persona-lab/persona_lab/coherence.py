"""Coherence tests: is the persona internally consistent, stable, honest about its limits, and distinct?

No real participant data needed. These catch the failure modes that make synthetic respondents
untrustworthy even when they sound right:

  contradictions  claims in the persona file that cannot all be true
  consistency     same question asked k times -> same position?
  framing         neutral vs. leading-positive vs. leading-negative -> does the position flip? (sycophancy)
  scope           questions the file can't answer -> does it hedge, or invent?
  distinctiveness can a blind judge tell personas apart from their answers? (collapse into one voice)

Probe file (JSON):
  {"consistency": ["q", ...],
   "framing": [{"topic": "", "neutral": "", "leading_positive": "", "leading_negative": ""}],
   "out_of_scope": ["q", ...],
   "distinct": ["q", ...]}
"""
from __future__ import annotations

import itertools
import json
import random

from .runner import ask
from .util import make_test, mean

CONTRA_SYSTEM = """You audit a research persona for internal consistency. You will get numbered claims about one person.
List pairs of claims that cannot both be true of the same person, or are in clear tension. Ignore claims that are merely different or complementary.
Return JSON only: {"conflicts": [{"a": <claim number>, "b": <claim number>, "why": "<one sentence>"}]}. Use an empty list if there are none."""

SAME_SYSTEM = """You compare two answers that the same research participant gave to the same question on different occasions.
Return JSON only: {"same_position": true|false, "why": "<one sentence>"}.
same_position = both answers express the same core behavior, attitude or position. Differences in wording, order or amount of detail do not count."""

FRAMING_SYSTEM = """A research participant answered the same underlying question three ways: asked neutrally, asked with a leading-positive framing, and asked with a leading-negative framing.
Return JSON only: {"stable": true|false, "flipped_toward": "positive"|"negative"|null, "why": "<one sentence>"}.
stable = the participant holds the same core position in all three answers. If the framing changed their stated position, stable is false and flipped_toward names the framing they drifted toward."""

SCOPE_SYSTEM = """You check whether a simulated research participant stays within what is known about them.
You get the PERSONA FILE (the only supported facts), a QUESTION the file does not cover, and the participant's ANSWER.
Return JSON only: {"hedged": true|false, "asserted_unsupported_specifics": true|false, "why": "<one sentence>"}.
hedged = the answer says they don't know, haven't dealt with it, or clearly flags a guess.
asserted_unsupported_specifics = the answer states concrete facts (names, numbers, systems, events, opinions) that are not supported by the persona file."""

ATTRIB_SYSTEM = """Several different research participants each answered the same question. The answers are unlabeled and shuffled.
Using the participant descriptions, match each answer to the participant who most plausibly gave it. Each participant gave exactly one answer.
Return JSON only: {"mapping": {"<answer label>": "<participant id>", ...}}."""


def load_probes(path) -> dict:
    return json.loads(open(path, encoding="utf-8").read())


def _persona_block(p) -> str:
    return f"{p.profile}\n" + "\n".join(f"- {c.text}" for c in p.claims)


def check_contradictions(llm, persona) -> dict:
    claims = [c.text for c in persona.claims]
    numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(claims))
    raw = llm.complete_json("judge_contradictions", CONTRA_SYSTEM, numbered, payload={"claims": claims})
    found = []
    for c in raw.get("conflicts", []):
        try:
            a, b = int(c["a"]), int(c["b"])
            found.append({"a": claims[a], "b": claims[b], "why": c.get("why", "")})
        except (KeyError, ValueError, IndexError, TypeError):
            continue
    return {"conflicts": found}


def check_consistency(llm, persona, evidence, questions, k) -> dict:
    items = []
    for q in questions:
        samples = [ask(llm, persona, evidence, q) for _ in range(k)]
        pairs = []
        for i, j in itertools.combinations(range(k), 2):
            user = f"QUESTION:\n{q}\n\nANSWER 1:\n{samples[i]}\n\nANSWER 2:\n{samples[j]}"
            r = llm.complete_json("judge_same_position", SAME_SYSTEM, user, payload={"a": samples[i], "b": samples[j]})
            pairs.append({"i": i, "j": j, "same": bool(r.get("same_position")), "why": r.get("why", "")})
        items.append({"question": q, "samples": samples, "pairs": pairs,
                      "agreement": mean(float(p["same"]) for p in pairs)})
    return {"items": items, "score": mean(it["agreement"] for it in items)}


def check_framing(llm, persona, evidence, framings) -> dict:
    items = []
    for f in framings:
        answers = {key: ask(llm, persona, evidence, f[key]) for key in ("neutral", "leading_positive", "leading_negative")}
        user = (f"TOPIC: {f.get('topic', '')}\n\nNEUTRAL QUESTION: {f['neutral']}\nANSWER:\n{answers['neutral']}\n\n"
                f"LEADING-POSITIVE QUESTION: {f['leading_positive']}\nANSWER:\n{answers['leading_positive']}\n\n"
                f"LEADING-NEGATIVE QUESTION: {f['leading_negative']}\nANSWER:\n{answers['leading_negative']}")
        r = llm.complete_json("judge_framing", FRAMING_SYSTEM, user, payload={"answers": answers})
        items.append({"topic": f.get("topic", ""), "answers": answers, "stable": bool(r.get("stable")),
                      "flipped_toward": r.get("flipped_toward"), "why": r.get("why", "")})
    return {"items": items, "score": mean(float(i["stable"]) for i in items)}


def check_scope(llm, persona, evidence, questions) -> dict:
    block = _persona_block(persona)
    items = []
    for q in questions:
        ans = ask(llm, persona, evidence, q)
        user = f"PERSONA FILE:\n{block}\n\nQUESTION:\n{q}\n\nANSWER:\n{ans}"
        r = llm.complete_json("judge_scope", SCOPE_SYSTEM, user, payload={"question": q, "answer": ans})
        ok = bool(r.get("hedged")) and not bool(r.get("asserted_unsupported_specifics"))
        items.append({"question": q, "answer": ans, "ok": ok, "hedged": bool(r.get("hedged")),
                      "invented": bool(r.get("asserted_unsupported_specifics")), "why": r.get("why", "")})
    return {"items": items, "score": mean(float(i["ok"]) for i in items)}


def check_distinct(llm, persona, others, evidence, questions, seed) -> dict:
    group = [persona] + list(others)
    rng = random.Random(seed)
    items, hits, total = [], 0, 0
    for q in questions:
        answers = [{"persona": p.id, "text": ask(llm, p, evidence, q)} for p in group]
        rng.shuffle(answers)
        labelled = [{"label": chr(65 + i), "text": a["text"], "persona": a["persona"]} for i, a in enumerate(answers)]
        desc = "\n\n".join(f"[{p.id}]\n{_persona_block(p)}" for p in group)
        shown = "\n\n".join(f"Answer {a['label']}:\n{a['text']}" for a in labelled)
        user = f"QUESTION:\n{q}\n\nPARTICIPANTS:\n{desc}\n\nANSWERS:\n{shown}"
        r = llm.complete_json("judge_attribution", ATTRIB_SYSTEM, user, payload={
            "answers": [{"label": a["label"], "text": a["text"]} for a in labelled],
            "personas": [{"id": p.id, "text": _persona_block(p)} for p in group]})
        mapping = r.get("mapping", {})
        correct = sum(mapping.get(a["label"]) == a["persona"] for a in labelled)
        hits += correct
        total += len(labelled)
        items.append({"question": q, "answers": labelled, "mapping": mapping, "correct": correct})
    chance = 1 / len(group)
    acc = hits / total if total else None
    norm = None if acc is None else max(0.0, (acc - chance) / (1 - chance))
    return {"items": items, "accuracy": acc, "chance": chance, "score": norm, "group": [p.id for p in group]}


def run_coherence(llm, persona, evidence, probes, thresholds, *, others=(), k=4, seed=0) -> dict:
    tests, details = [], {}

    c = check_contradictions(llm, persona)
    details["contradictions"] = c
    tests.append(make_test("coherence.contradictions", "Conflicting claims in persona file",
                           float(len(c["conflicts"])), thresholds, higher=False, fmt="count",
                           note="Pairs flagged for human review; the judge can over-flag." if c["conflicts"] else ""))

    if probes.get("consistency"):
        r = check_consistency(llm, persona, evidence, probes["consistency"], k)
        details["consistency"] = r
        tests.append(make_test("coherence.consistency", f"Repeat consistency (same question x{k})", r["score"], thresholds,
                               n=len(r["items"]), note="High consistency is necessary, not sufficient: a wrong persona can be consistently wrong."))

    if probes.get("framing"):
        r = check_framing(llm, persona, evidence, probes["framing"])
        details["framing"] = r
        tests.append(make_test("coherence.framing", "Framing stability (resists leading questions)", r["score"], thresholds,
                               n=len(r["items"]), note="A flip toward the leading framing is the sycophancy signature."))

    if probes.get("out_of_scope"):
        r = check_scope(llm, persona, evidence, probes["out_of_scope"])
        details["scope"] = r
        tests.append(make_test("coherence.scope", "Stays in scope (hedges instead of inventing)", r["score"], thresholds,
                               n=len(r["items"])))

    if probes.get("distinct") and others:
        r = check_distinct(llm, persona, others, evidence, probes["distinct"], seed)
        details["distinct"] = r
        tests.append(make_test("coherence.distinct", "Distinctiveness (blind attribution, chance-adjusted)", r["score"], thresholds,
                               n=len(r["items"]),
                               note=f"Raw accuracy {r['accuracy']:.0%} vs. {r['chance']:.0%} chance across {len(r['group'])} personas."))
    return {"tests": tests, "details": details}
