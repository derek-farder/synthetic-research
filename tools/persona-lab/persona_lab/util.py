"""Shared helpers: tokenizing, small stats, thresholds, grading."""
from __future__ import annotations

import json
import random
import re
import statistics
from pathlib import Path

_TOKEN = re.compile(r"[a-z0-9']+")
_STOP = set(
    "a an and the of to in on for is are was were be been being it its that this these those "
    "i we you they he she my our your their with as at by or but not so if then than from have "
    "has had do does did can could would should will just about into very really me us them only any all some".split()
)
HEDGE = re.compile(
    r"(not sure|don'?t know|do not know|no idea|haven'?t (dealt|seen|had)|outside (of )?(what|my)|"
    r"i'?d (just )?be guessing|just guessing|i'?m guessing|extrapolat|can'?t speak to|couldn'?t say)",
    re.I,
)
_CATEGORY = re.compile(r"^[a-z]+:\s+", re.I)


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def containment(a: str, b: str) -> float:
    """Share of a's content tokens that also appear in b."""
    ta, tb = set(tokens(a)), set(tokens(b))
    return len(ta & tb) / len(ta) if ta else 0.0


def jaccard(a: str, b: str) -> float:
    ta, tb = set(tokens(a)), set(tokens(b))
    return len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0


def is_hedged(text: str) -> bool:
    return bool(HEDGE.search(text))


def strip_category(claim: str) -> str:
    return _CATEGORY.sub("", claim)


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def std(xs) -> float:
    xs = list(xs)
    return statistics.pstdev(xs) if len(xs) > 1 else 0.0


def bootstrap_ci(values, iters: int = 2000, seed: int = 0, alpha: float = 0.10):
    """Percentile bootstrap CI of the mean. Returns None with fewer than 2 values."""
    vals = list(values)
    if len(vals) < 2:
        return None
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(vals) for _ in vals) / len(vals) for _ in range(iters))
    return means[int(alpha / 2 * iters)], means[int((1 - alpha / 2) * iters) - 1]


# (pass_at, warn_at). These are starting heuristics, NOT validated cut-offs.
# Calibrate them against personas you already trust or distrust (see README).
DEFAULT_THRESHOLDS = {
    "lint.errors": (0, 0),
    "lint.grounded": (0.90, 0.70),
    "lint.thick": (0.60, 0.40),
    "backtest.leakage": (0, 0),
    "backtest.stance": (0.60, 0.45),
    "backtest.lift": (0.10, 0.00),
    "backtest.contradiction": (0.10, 0.25),
    "backtest.abstain": (0.25, 0.40),
    "coherence.contradictions": (0, 2),
    "coherence.consistency": (0.80, 0.65),
    "coherence.framing": (0.80, 0.60),
    "coherence.scope": (0.80, 0.60),
    "coherence.distinct": (0.60, 0.30),
}


def load_thresholds(path: str | None) -> dict:
    t = dict(DEFAULT_THRESHOLDS)
    if path:
        for k, v in json.loads(Path(path).read_text()).items():
            t[k] = tuple(v)
    return t


def grade(score, pass_at, warn_at, higher_is_better: bool = True) -> str:
    if score is None:
        return "SKIP"
    if higher_is_better:
        return "PASS" if score >= pass_at else "WARN" if score >= warn_at else "FAIL"
    return "PASS" if score <= pass_at else "WARN" if score <= warn_at else "FAIL"


def _fmt(x, kind: str) -> str:
    if x is None:
        return "n/a"
    if kind == "pts":
        return f"{x * 100:+.0f} pts"
    if kind == "count":
        return f"{x:.0f}"
    return f"{x * 100:.0f}%"


def make_test(tid, label, score, thresholds, *, higher=True, fmt="pct", note="", ci=None, n=None):
    pass_at, warn_at = thresholds[tid]
    op = "≥" if higher else "≤"
    return {
        "id": tid,
        "label": label,
        "score": score,
        "display": _fmt(score, fmt),
        "ci": [round(ci[0], 3), round(ci[1], 3)] if ci else None,
        "ci_display": f"{_fmt(ci[0], fmt)}–{_fmt(ci[1], fmt)}" if ci else "",
        "n": n,
        "criterion": f"PASS {op} {_fmt(pass_at, fmt)} · WARN {op} {_fmt(warn_at, fmt)}",
        "verdict": grade(score, pass_at, warn_at, higher),
        "note": note,
    }


def overall(tests: list[dict]) -> str:
    verdicts = {t["verdict"] for t in tests}
    if any(t["id"] == "backtest.leakage" and t["verdict"] == "FAIL" for t in tests):
        return "INVALID"
    if "FAIL" in verdicts:
        return "FAIL"
    if "WARN" in verdicts:
        return "WARN"
    return "PASS"
