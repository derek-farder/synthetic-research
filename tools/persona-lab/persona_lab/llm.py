"""LLM access layer.

Two backends:
  * AnthropicLLM - real calls through the Anthropic API.
  * MockLLM      - deterministic lexical stand-in so the harness itself can be tested
                   without an API key or spend. Its scores say nothing about persona quality.

Every call carries a `task` name and a structured `payload`. The real backend ignores the
payload (the prompt already contains everything); the mock uses it instead of parsing prompts.
"""
from __future__ import annotations

import json
import os
import random
import re

from .util import containment, is_hedged, jaccard, strip_category, tokens


def extract_json(text: str):
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        s, e = text.find(opener), text.rfind(closer)
        if s != -1 and e > s:
            try:
                return json.loads(text[s : e + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"no JSON in model reply: {text[:200]!r}")


class LLM:
    mock = False
    model = "?"
    judge_model = "?"

    def complete(self, task, system, user, *, payload=None, history=None,
                 temperature=0.7, max_tokens=700, judge=False) -> str:
        raise NotImplementedError

    def complete_json(self, task, system, user, *, payload=None, retries=1, max_tokens=900):
        last = None
        for _ in range(retries + 1):
            raw = self.complete(task, system, user, payload=payload, temperature=0.0,
                                max_tokens=max_tokens, judge=True)
            try:
                return extract_json(raw)
            except ValueError as e:
                last = e
        raise last


class AnthropicLLM(LLM):
    def __init__(self, model: str | None = None, judge_model: str | None = None):
        try:
            import anthropic
        except ImportError:
            raise SystemExit("The 'anthropic' package is required: pip install anthropic (or use --mock).")
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("PERSONA_LAB_MODEL", "claude-sonnet-5-5")
        self.judge_model = judge_model or os.environ.get("PERSONA_LAB_JUDGE_MODEL", self.model)

    def complete(self, task, system, user, *, payload=None, history=None,
                 temperature=0.7, max_tokens=700, judge=False) -> str:
        messages = list(history or []) + [{"role": "user", "content": user}]
        resp = self.client.messages.create(
            model=self.judge_model if judge else self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


class MockLLM(LLM):
    """Lexical stand-in. Exercises every code path; measures nothing real."""

    mock = True
    model = "mock"
    judge_model = "mock"

    def __init__(self, seed: int = 7):
        self.rng = random.Random(seed)

    def complete(self, task, system, user, *, payload=None, history=None,
                 temperature=0.7, max_tokens=700, judge=False) -> str:
        handler = getattr(self, f"_{task}", None)
        if handler is None:
            raise ValueError(f"MockLLM has no handler for task '{task}'")
        return handler(payload or {})

    # ---- persona side -------------------------------------------------
    def _persona_answer(self, p):
        claims, q = p.get("claims", []), p["question"]
        if p.get("baseline") or not claims:
            return "Honestly it depends on the day. I'd have to see how it plays out before I could say much."
        qt = set(tokens(q))
        scored = sorted(((len(qt & set(tokens(c))), self.rng.random(), c) for c in claims), reverse=True)
        if scored[0][0] == 0:
            return "I'm not sure, that's outside what I've dealt with, so I'd just be guessing."
        pick = [scored[0][2]]
        if len(scored) > 1 and scored[1][0] > 0 and self.rng.random() < 0.6:
            pick.append(scored[1][2])
        if len(scored) > 1 and self.rng.random() < 0.2:  # occasional drift gives the consistency test something to find
            pick = [scored[1][2]]
        return "From what I've seen: " + " ".join(strip_category(c) for c in pick)

    # ---- judges (all lexical) -----------------------------------------
    def _judge_match(self, p):
        real, syn = p["real"], p["synthetic"]
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", real) if len(tokens(s)) >= 4]
        points = [{"point": s, "covered": containment(s, syn) >= 0.30} for s in sentences[:5]]
        c = containment(real, syn)
        if is_hedged(syn):
            stance = "abstained"
        else:
            stance = "match" if c >= 0.30 else "partial" if c >= 0.12 else "mismatch"
        return json.dumps({"points": points, "stance": stance, "contradicts": False})

    def _judge_contradictions(self, p):
        claims, conflicts = p["claims"], []
        bodies = [strip_category(c) for c in claims]
        absolute = re.compile(r"\b(never|always)\b", re.I)
        for i, a in enumerate(bodies):
            if not absolute.search(a):
                continue
            for j, b in enumerate(bodies):
                if i == j or absolute.search(b):
                    continue
                shared = set(tokens(a)) & set(tokens(b))
                if len(shared) >= 2:
                    conflicts.append({"a": i, "b": j, "why": f"(mock) absolute claim overlaps on: {', '.join(sorted(shared)[:4])}"})
        return json.dumps({"conflicts": conflicts})

    def _judge_same_position(self, p):
        same = jaccard(p["a"], p["b"]) >= 0.25
        return json.dumps({"same_position": same, "why": "(mock) lexical overlap"})

    def _judge_framing(self, p):
        a = p["answers"]
        pairs = [("neutral", "leading_positive"), ("neutral", "leading_negative"), ("leading_positive", "leading_negative")]
        stable = min(jaccard(a[x], a[y]) for x, y in pairs) >= 0.20
        flipped = None
        if not stable:
            flipped = "positive" if jaccard(a["neutral"], a["leading_positive"]) < jaccard(a["neutral"], a["leading_negative"]) else "negative"
        return json.dumps({"stable": stable, "flipped_toward": flipped, "why": "(mock) lexical overlap"})

    def _judge_scope(self, p):
        hedged = is_hedged(p["answer"])
        return json.dumps({"hedged": hedged, "asserted_unsupported_specifics": not hedged, "why": "(mock) hedge-phrase check"})

    def _judge_attribution(self, p):
        answers, personas = p["answers"], p["personas"]
        pairs = sorted(((len(set(tokens(a["text"])) & set(tokens(q["text"]))), a["label"], q["id"])
                        for a in answers for q in personas), reverse=True)
        mapping, used_a, used_p = {}, set(), set()
        for _, label, pid in pairs:
            if label not in used_a and pid not in used_p:
                mapping[label] = pid
                used_a.add(label)
                used_p.add(pid)
        return json.dumps({"mapping": mapping})
