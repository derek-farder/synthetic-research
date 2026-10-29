"""Backtest: can the persona reproduce what real participants (held out from its grounding) actually said?

Method
  1. Leakage check - holdout interviews must not have been used to build the persona.
  2. For every held-out question, the persona answers n times (fresh samples).
  3. A judge compares each answer to the real answer: stance match, point coverage, contradiction.
  4. The same is done for a role-only baseline (no evidence). The persona has to beat it,
     otherwise the evidence is adding nothing a generic prompt wouldn't.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .runner import ask
from .util import bootstrap_ci, make_test, mean, std

JUDGE_MATCH_SYSTEM = """You compare a SYNTHETIC answer with what a REAL research participant said to the same question. Judge only against the real answer. Do not reward fluency, or detail the real participant never gave.

Return JSON only:
{"points": [{"point": "<substantive point the real participant made>", "covered": true|false}],
 "stance": "match" | "partial" | "mismatch" | "abstained",
 "contradicts": true|false}

- points: 1 to 5 distinct substantive points from the REAL answer. covered = the synthetic answer makes the same point (paraphrase counts).
- stance: the overall position, behavior or attitude. match = same. partial = overlapping but with materially different emphasis. mismatch = different. abstained = the synthetic answer declines to answer or says it doesn't know.
- contradicts: true only if the synthetic answer asserts something directly opposite to something the real participant said."""

STANCE_VALUE = {"match": 1.0, "partial": 0.5, "mismatch": 0.0, "abstained": 0.0}


def load_holdouts(path, persona_id=None) -> list:
    p = Path(path)
    files = sorted(p.glob("*.json")) if p.is_dir() else [p]
    out = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        for item in data if isinstance(data, list) else [data]:
            if persona_id and item.get("persona_id") not in (None, persona_id):
                continue
            out.append(item)
    return out


def _ngrams(text: str, n: int) -> set:
    w = re.findall(r"[a-z0-9']+", text.lower())
    return {" ".join(w[i : i + n]) for i in range(len(w) - n + 1)}


def find_leaks(evidence: dict, holdouts: list, n: int = 6) -> list:
    ev_grams = set()
    for e in evidence.values():
        ev_grams |= _ngrams(e["quote"], n)
    hold_ids = {h["id"] for h in holdouts}
    leaks = []
    for e_id, e in evidence.items():
        if e["source"] in hold_ids:
            leaks.append({"kind": "source", "evidence": e_id, "holdout": e["source"],
                          "detail": "Evidence item comes from a holdout interview."})
    for h in holdouts:
        for ti, t in enumerate(h["turns"]):
            shared = _ngrams(t["a"], n) & ev_grams
            if shared:
                leaks.append({"kind": "text", "holdout": h["id"], "turn": ti,
                              "detail": f"Holdout answer shares {len(shared)} {n}-word run(s) with evidence, e.g. '{sorted(shared)[0]}'"})
    return leaks


def judge_match(llm, question: str, real: str, synthetic: str) -> dict:
    user = f"QUESTION:\n{question}\n\nREAL ANSWER:\n{real}\n\nSYNTHETIC ANSWER:\n{synthetic}"
    raw = llm.complete_json("judge_match", JUDGE_MATCH_SYSTEM, user,
                            payload={"question": question, "real": real, "synthetic": synthetic})
    stance = raw.get("stance", "mismatch")
    if stance not in STANCE_VALUE:
        stance = "mismatch"
    points = [p for p in raw.get("points", []) if isinstance(p, dict)]
    covered = [bool(p.get("covered")) for p in points]
    return {
        "stance": stance,
        "stance_score": STANCE_VALUE[stance],
        "coverage": (sum(covered) / len(covered)) if covered else None,
        "contradicts": bool(raw.get("contradicts")),
        "points": points,
    }


def _aggregate(samples: list) -> dict:
    cov = [s["coverage"] for s in samples if s["coverage"] is not None]
    return {
        "stance": mean(s["stance_score"] for s in samples),
        "coverage": mean(cov),
        "contradiction": mean(float(s["contradicts"]) for s in samples),
        "abstain": mean(float(s["stance"] == "abstained") for s in samples),
        "spread": std(s["stance_score"] for s in samples),
    }


def run_backtest(llm, persona, evidence, holdouts, thresholds, *, n_samples=3, use_history=False, baseline=True) -> dict:
    leaks = find_leaks(evidence, holdouts)
    turns = []
    for h in holdouts:
        history = []
        for ti, t in enumerate(h["turns"]):
            samples, base = [], []
            for _ in range(n_samples):
                ans = ask(llm, persona, evidence, t["q"], history=history if use_history else None)
                samples.append({"answer": ans, **judge_match(llm, t["q"], t["a"], ans)})
                if baseline:
                    b = ask(llm, persona, evidence, t["q"], baseline=True)
                    base.append({"answer": b, **judge_match(llm, t["q"], t["a"], b)})
            turns.append({
                "holdout": h["id"], "turn": ti, "question": t["q"], "real": t["a"],
                "samples": samples, "baseline_samples": base,
                "agg": _aggregate(samples), "baseline_agg": _aggregate(base) if base else None,
            })
            history += [{"role": "user", "content": t["q"]}, {"role": "assistant", "content": t["a"]}]

    n_turns = len(turns)
    stance = [t["agg"]["stance"] for t in turns]
    lifts = [t["agg"]["stance"] - t["baseline_agg"]["stance"] for t in turns if t["baseline_agg"]]
    power = "" if n_turns >= 10 else f" LOW POWER: only {n_turns} held-out answers; treat the verdict as a smoke signal, not a measurement."

    tests = [
        make_test("backtest.leakage", "Holdout contamination (leaks found)", float(len(leaks)), thresholds,
                  higher=False, fmt="count",
                  note="Any leak invalidates the backtest: the persona may have seen the answers." if leaks else ""),
        make_test("backtest.stance", "Stance match vs. real holdout answers", mean(stance), thresholds,
                  ci=bootstrap_ci(stance), n=n_turns, note="match=1, partial=0.5, mismatch/abstained=0." + power),
    ]
    if baseline:
        tests.append(make_test("backtest.lift", "Lift over role-only baseline", mean(lifts), thresholds, fmt="pts",
                               ci=bootstrap_ci(lifts), n=len(lifts),
                               note="Persona stance score minus a baseline given only the role title." + power))
    tests += [
        make_test("backtest.contradiction", "Answers that contradict the real participant",
                  mean(t["agg"]["contradiction"] for t in turns), thresholds, higher=False),
        make_test("backtest.abstain", "Abstention rate (persona says it doesn't know)",
                  mean(t["agg"]["abstain"] for t in turns), thresholds, higher=False,
                  note="High abstention can hide a thin persona behind safe non-answers."),
    ]
    return {
        "tests": tests,
        "turns": turns,
        "leaks": leaks,
        "summary": {
            "n_turns": n_turns, "n_samples": n_samples,
            "coverage": mean(t["agg"]["coverage"] for t in turns if t["agg"]["coverage"] is not None),
            "mean_spread": mean(t["agg"]["spread"] for t in turns),
            "history": use_history,
        },
    }
