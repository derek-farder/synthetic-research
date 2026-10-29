"""Persona runner: turns a persona file into a simulated interview participant."""
from __future__ import annotations

from .persona import Persona

RUNNER_SYSTEM = """You are role-playing one research participant so a researcher can test an interview guide before fieldwork. You are not an assistant.

Rules:
1. Speak in first person, conversationally, in 2-5 sentences. No lists, no headings.
2. Everything you say about your work, habits, constraints and opinions must come from the PERSONA FILE below. Do not add biographical detail, numbers, or named tools that are not in it.
3. If the question is about something the file does not cover, say you don't know or haven't dealt with it, or give a clearly flagged guess ("I'm guessing here, but...").
4. Describe what you actually do or did rather than what you would hypothetically do. Do not be agreeable for its own sake: if the interviewer's framing doesn't match your experience, say so.
5. Never mention the persona file, the evidence, or that you are simulated.

PERSONA FILE
Role: {role}
{profile}

What is known about this person:
{claims}
"""

BASELINE_SYSTEM = """You are role-playing a {role} in a research interview. Answer the interviewer's questions the way such a person plausibly would: first person, conversational, 2-5 sentences. Do not mention that you are simulated."""


def system_prompt(persona: Persona, evidence: dict, baseline: bool = False) -> str:
    if baseline:
        return BASELINE_SYSTEM.format(role=persona.role or persona.name)
    lines = []
    for c in persona.claims:
        tag = "" if c.evidence else " (inferred, no direct evidence)"
        lines.append(f"- {c.text}{tag}")
        for e in c.evidence:
            if e in evidence and evidence[e]["quote"]:
                lines.append(f'    quote: "{evidence[e]["quote"]}"')
    return RUNNER_SYSTEM.format(role=persona.role or persona.name, profile=persona.profile, claims="\n".join(lines))


def ask(llm, persona: Persona, evidence: dict, question: str, *, history=None,
        temperature: float = 0.8, baseline: bool = False) -> str:
    payload = {"question": question, "baseline": baseline, "claims": [c.text for c in persona.claims]}
    return llm.complete(
        "persona_answer",
        system_prompt(persona, evidence, baseline),
        question,
        payload=payload,
        history=history,
        temperature=temperature,
        max_tokens=400,
    ).strip()
