"""Command line interface: lint, backtest, coherence, all."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from .backtest import load_holdouts, run_backtest
from .coherence import load_probes, run_coherence
from .llm import AnthropicLLM, MockLLM
from .persona import lint, load_evidence, load_persona, load_personas_dir
from .report import render
from .util import load_thresholds, make_test, overall


def _llm(args):
    if args.mock:
        return MockLLM(seed=args.seed)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Set it, or pass --mock to smoke-test the harness (mock scores are meaningless).")
    return AnthropicLLM(model=args.model, judge_model=args.judge_model)


def _lint_tests(persona, evidence, thresholds):
    res = lint(persona, evidence)
    tests = [
        make_test("lint.errors", "Grounding errors (bad or circular evidence)", float(res["errors"]), thresholds, higher=False, fmt="count"),
        make_test("lint.grounded", "Claims with at least one real evidence item", res["grounded"], thresholds, n=res["n_claims"]),
        make_test("lint.thick", "Claims with two or more real evidence items", res["thick"], thresholds, n=res["n_claims"]),
    ]
    return res, tests


def _emit(results, args):
    results["overall"] = overall(results["tests"])
    out_dir = Path(args.out) if args.out else Path("reports") / f"{results['meta']['persona']}-{datetime.now():%Y%m%d-%H%M%S}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(render(results), encoding="utf-8")
    (out_dir / "results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    if results["meta"]["mock"]:
        print("** MOCK RUN: lexical stand-in, scores are not meaningful **\n")
    width = max(len(t["label"]) for t in results["tests"])
    for t in results["tests"]:
        ci = f"  [{t['ci_display']}]" if t["ci_display"] else ""
        print(f"  {t['verdict']:<5} {t['label']:<{width}}  {t['display']}{ci}")
    print(f"\nOverall: {results['overall']}\nReport:  {out_dir / 'report.md'}")
    return {"PASS": 0, "WARN": 0, "FAIL": 1, "INVALID": 2}[results["overall"]]


def _meta(persona, llm, args):
    return {"persona": persona.id, "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "mock": bool(llm and llm.mock), "model": llm.model if llm else "n/a (no model calls)",
            "judge_model": llm.judge_model if llm else "n/a", "seed": args.seed}


def cmd_run(args) -> int:
    persona = load_persona(args.persona)
    evidence = load_evidence(args.evidence)
    thresholds = load_thresholds(args.thresholds)
    do = args.command
    llm = None if do == "lint" else _llm(args)
    results = {"meta": _meta(persona, llm, args), "tests": [], "sections": {}}

    if do in ("lint", "all"):
        res, tests = _lint_tests(persona, evidence, thresholds)
        results["tests"] += tests
        results["sections"]["lint"] = res

    if do in ("backtest", "all"):
        if not args.holdout:
            sys.exit("--holdout is required for backtest")
        holdouts = load_holdouts(args.holdout, persona.id)
        if not holdouts:
            sys.exit(f"No holdout interviews found for persona '{persona.id}' in {args.holdout}")
        bt = run_backtest(llm, persona, evidence, holdouts, thresholds, n_samples=args.n,
                          use_history=args.history, baseline=not args.no_baseline)
        results["tests"] += bt.pop("tests")
        results["sections"]["backtest"] = bt

    if do in ("coherence", "all"):
        if not args.probes:
            sys.exit("--probes is required for coherence")
        others = load_personas_dir(args.others, exclude_id=persona.id) if args.others else []
        co = run_coherence(llm, persona, evidence, load_probes(args.probes), thresholds,
                           others=others, k=args.k, seed=args.seed)
        results["tests"] += co.pop("tests")
        results["sections"]["coherence"] = co.pop("details")

    return _emit(results, args)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="persona-lab", description="Backtest and coherence-test synthetic research personas.")
    sub = ap.add_subparsers(dest="command", required=True)
    for name, help_ in (("lint", "static grounding checks (no model calls)"),
                        ("backtest", "compare persona answers to held-out real interviews"),
                        ("coherence", "consistency, framing, scope and distinctiveness probes"),
                        ("all", "run everything")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--persona", required=True, help="persona markdown file")
        p.add_argument("--evidence", help="evidence JSON file")
        p.add_argument("--holdout", help="holdout interview JSON file or folder (backtest)")
        p.add_argument("--probes", help="probe JSON file (coherence)")
        p.add_argument("--others", help="folder of other personas for the distinctiveness test")
        p.add_argument("--n", type=int, default=3, help="samples per held-out question (default 3)")
        p.add_argument("--k", type=int, default=4, help="repeats per consistency question (default 4)")
        p.add_argument("--history", action="store_true", help="supply prior real turns as conversation history")
        p.add_argument("--no-baseline", action="store_true", help="skip the role-only baseline")
        p.add_argument("--thresholds", help="JSON file overriding default thresholds")
        p.add_argument("--out", help="output folder (default reports/<persona>-<timestamp>)")
        p.add_argument("--seed", type=int, default=7)
        p.add_argument("--model", help="persona model (env PERSONA_LAB_MODEL)")
        p.add_argument("--judge-model", help="judge model (env PERSONA_LAB_JUDGE_MODEL)")
        p.add_argument("--mock", action="store_true", help="use the lexical mock instead of the API")
        p.set_defaults(func=cmd_run)
    args = ap.parse_args(argv)
    return args.func(args)
