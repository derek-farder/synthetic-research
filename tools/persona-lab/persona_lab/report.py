"""Markdown rendering of test results. Raw answers are included on purpose: read them."""
from __future__ import annotations

ICON = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL", "SKIP": "skip", "INVALID": "INVALID"}


def _cell(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def _quote(s: str) -> str:
    return "\n".join("> " + line for line in str(s).strip().splitlines())


def render(results: dict) -> str:
    meta = results["meta"]
    out = [f"# Persona test report: {meta['persona']}",
           f"_Generated {meta['generated']} · model `{meta['model']}` · judge `{meta['judge_model']}` · seed {meta['seed']}_", ""]
    if meta["mock"]:
        out += ["> **MOCK RUN.** Answers and judgments came from a lexical stand-in, not a model. "
                "This verifies the harness works; the scores say nothing about the persona.", ""]
    out += [f"## Overall: {ICON[results['overall']]}", ""]
    if results["overall"] == "INVALID":
        out += ["The backtest is invalid because holdout data leaked into the persona's grounding. Fix that before reading anything else.", ""]
    out += ["PASS means no problem was detected by these probes. It does not mean the persona is valid; "
            "validity comes from agreement with real participants over time.", ""]

    out += ["| Test | Result | 90% CI | n | Verdict | Criterion |", "|---|---|---|---|---|---|"]
    for t in results["tests"]:
        out.append(f"| {_cell(t['label'])} | {t['display']} | {t['ci_display'] or '-'} | {t['n'] if t['n'] is not None else '-'} "
                   f"| **{ICON[t['verdict']]}** | {t['criterion']} |")
    out.append("")
    notes = [t for t in results["tests"] if t["note"]]
    if notes:
        out += ["### Notes", ""] + [f"- **{t['label']}:** {t['note']}" for t in notes] + [""]

    lint = results["sections"].get("lint")
    if lint:
        out += ["## Grounding (lint)", "",
                f"{lint['n_claims']} claims · {lint['grounded']:.0%} have at least one real evidence item · "
                f"{lint['thick']:.0%} have two or more.", ""]
        shown = [i for i in lint["issues"] if i["level"] != "info"]
        if shown:
            for i in shown:
                out.append(f"- **{i['level'].upper()} {i['code']}**: {i['message']}" + (f"  \n  _Claim:_ {i['claim']}" if i["claim"] else ""))
            out.append("")
        else:
            out += ["No grounding issues.", ""]

    bt = results["sections"].get("backtest")
    if bt:
        s = bt["summary"]
        out += ["## Backtest detail", "",
                f"{s['n_turns']} held-out answers × {s['n_samples']} samples each"
                + (" · prior real turns supplied as history" if s["history"] else "")
                + (f" · mean point coverage {s['coverage']:.0%}" if s["coverage"] is not None else "")
                + (f" · mean sample-to-sample spread {s['mean_spread']:.2f}" if s["mean_spread"] is not None else ""), ""]
        for lk in bt["leaks"]:
            out.append(f"- **LEAK** ({lk['kind']}, holdout `{lk['holdout']}`): {lk['detail']}")
        if bt["leaks"]:
            out.append("")
        for t in bt["turns"]:
            a, b = t["agg"], t["baseline_agg"]
            line = f"stance {a['stance']:.2f}" + (f" vs. baseline {b['stance']:.2f}" if b else "")
            out += [f"### [{t['holdout']} · Q{t['turn'] + 1}] {t['question']}", "",
                    "**Real participant**", _quote(t["real"]), "",
                    "**Synthetic (sample 1)**", _quote(t["samples"][0]["answer"]), "",
                    f"Stances across samples: {', '.join(x['stance'] for x in t['samples'])} · {line}", ""]

    co = results["sections"].get("coherence")
    if co:
        out += ["## Coherence detail", ""]
        c = co.get("contradictions")
        if c is not None:
            out += ["### Conflicting claims", ""]
            out += ([f"- {x['a']}\n  vs. {x['b']}\n  _{x['why']}_" for x in c["conflicts"]] or ["None flagged."]) + [""]
        r = co.get("consistency")
        if r:
            out += ["### Repeat consistency", ""]
            for it in r["items"]:
                out += [f"**{it['question']}** · agreement {it['agreement']:.0%}", ""]
                for n, smp in enumerate(it["samples"][:2], 1):
                    out += [f"Sample {n}", _quote(smp), ""]
        r = co.get("framing")
        if r:
            out += ["### Framing stability", ""]
            for it in r["items"]:
                flag = "stable" if it["stable"] else f"UNSTABLE, drifted toward {it['flipped_toward'] or '?'}"
                out += [f"**{it['topic']}**: {flag}", ""]
                for key in ("neutral", "leading_positive", "leading_negative"):
                    out += [f"_{key}_", _quote(it["answers"][key]), ""]
        r = co.get("scope")
        if r:
            out += ["### Scope discipline", ""]
            for it in r["items"]:
                status = "OK" if it["ok"] else ("INVENTED" if it["invented"] else "NO HEDGE")
                out += [f"**{it['question']}** · {status}", _quote(it["answer"]), ""]
        r = co.get("distinct")
        if r:
            out += ["### Distinctiveness", "", f"Personas compared: {', '.join(r['group'])}.", ""]
            for it in r["items"]:
                out += [f"**{it['question']}** · {it['correct']}/{len(it['answers'])} attributed correctly", ""]
    return "\n".join(out)
