# persona-lab

A test harness for synthetic research personas. It answers two questions:

1. **Backtest:** does the persona reproduce what real participants, held out from its grounding, actually said?
2. **Coherence:** is the persona internally consistent, resistant to leading questions, honest about what it doesn't know, and distinguishable from other personas?

No dependencies for the harness itself. The `anthropic` package is needed only for real runs.

## Quick start

```bash
# Smoke test with the built-in mock (no API key, no cost). Scores are NOT meaningful.
python -m persona_lab all \
  --persona examples/personas/dana_charge_nurse.md \
  --others examples/personas \
  --evidence examples/evidence.json \
  --holdout examples/holdout \
  --probes examples/probes.json \
  --mock

# Real run
pip install anthropic
export ANTHROPIC_API_KEY=...
python -m persona_lab all --persona ... (same flags, without --mock)
```

Subcommands: `lint` (no model calls), `backtest`, `coherence`, `all`. Output goes to `reports/<persona>-<timestamp>/` as `report.md` (read this) and `results.json`. Exit code is 0 for PASS/WARN, 1 for FAIL, 2 for INVALID (holdout leaked), so it works in CI.

Env vars: `PERSONA_LAB_MODEL` (default `claude-sonnet-5-5`), `PERSONA_LAB_JUDGE_MODEL` (default: same as persona model).

The example personas, quotes and interviews are fictional. `dana_charge_nurse.md` has two seeded defects (an ungrounded claim that contradicts a grounded one, and a citation to a nonexistent evidence id) so you can watch the tools catch them.

## Inputs

**Persona** (`.md`): frontmatter (`id`, `name`, `role`), a `## Profile`, and a `## Claims` list. One claim per line, citing evidence ids, optionally prefixed with a category (`behavior`, `workaround`, `constraint`, `distrust`, `goal`, `context`):

```
- [E3] workaround: Carries a self-made laminated programming card.
- [] goal: A claim with no evidence is allowed, and flagged.
```

**Evidence** (`.json`): `{"E3": {"quote": "...", "source": "int_02", "synthetic": false}}`. Mark anything model-generated `"synthetic": true`; grounding a persona on synthetic output is flagged as circular.

**Holdout** (`.json`, file or folder): `{"id": "int_H1", "persona_id": "dana", "turns": [{"q": "...", "a": "..."}]}`. `persona_id` may be null to apply to any persona.

**Probes** (`.json`): `consistency` (questions), `framing` (neutral / leading_positive / leading_negative triples), `out_of_scope` (questions the file can't answer), `distinct` (questions all personas answer). See `examples/probes.json`.

## What each test does and what a failure means

| Test | Method | A fail usually means |
|---|---|---|
| Holdout contamination | 6-word text overlap between holdout answers and evidence, plus evidence sourced from a holdout interview | The backtest is invalid. Rebuild the persona without those interviews. |
| Stance match | Judge compares persona answers (n samples each) to the real answer | The persona doesn't behave like the people it's meant to represent. |
| Lift over baseline | Same test for a persona given only its role title | The evidence adds nothing a generic prompt wouldn't. |
| Contradiction / abstention | Judge flags answers that oppose the real one; counts "I don't know" | Contradiction: wrong persona. High abstention: thin persona hiding behind safe answers. |
| Conflicting claims | Judge reads the claims for pairs that can't both be true | Fix the file. The judge can over-flag, so review each pair. |
| Repeat consistency | Same question x k, pairwise "same position?" | Unstable persona; findings from single runs are unreliable. |
| Framing stability | Neutral vs. leading-positive vs. leading-negative | Sycophancy: the persona agrees with whatever the interviewer implies. |
| Scope | Questions outside the file; does it hedge or invent? | The persona fabricates fluently where evidence is absent. |
| Distinctiveness | Blind judge matches shuffled answers back to personas | Personas collapsed into one generic voice. |
| Lint | Static: missing/synthetic evidence, ungrounded and thin claims | Grounding problems you can fix without any model calls. |

## How to use this without fooling yourself

- **Split before you build.** Hold out interviews before building the persona. Hold-out that happens after you've read everything isn't a hold-out.
- **Sample size.** Under 10 held-out answers the tool prints LOW POWER, and the 90% bootstrap CI will be wide. Take the verdict as a smoke signal.
- **Run a negative control.** Point a persona at a holdout from a different segment (set `persona_id` to null). Its stance score should drop. If it doesn't, the backtest can't discriminate and you shouldn't trust its passes.
- **Calibrate the thresholds.** The defaults in `util.py` are starting guesses, not validated cut-offs. Override with `--thresholds file.json` (`{"backtest.stance": [0.55, 0.40]}`) once you've seen scores for a persona you trust and one you don't.
- **Use a different judge model when you can.** The same model as persona and judge shares its blind spots. Set `PERSONA_LAB_JUDGE_MODEL`.
- **Read the transcripts.** The report includes raw answers beside the real ones. The numbers tell you where to look; they don't replace looking.
- **PASS is the absence of detected problems.** It is not validity. Coherence tests in particular can't tell you the persona is right, only that it isn't visibly broken.

## Known limits

- Judges are LLMs and carry their own error. Spot-check a sample of judge decisions against your own reading before relying on any aggregate.
- Backtest questions are asked cold by default. Real interviews build on earlier answers; `--history` feeds prior real turns in, which is more realistic but lets earlier real answers shape later ones.
- Calls run sequentially. The example set is roughly 130 short model calls; lower `--n` and `--k` to trade rigor for speed and cost.
- The mock backend is lexical and exists to test the plumbing. Its scores, including its pass on distinctiveness and its flags on scope, say nothing about any real persona.

## Layout

```
persona_lab/
  persona.py    persona/evidence loading + lint
  runner.py     persona (and baseline) system prompts, ask()
  backtest.py   leakage check, holdout comparison, baseline lift
  coherence.py  contradiction, consistency, framing, scope, distinctiveness
  llm.py        Anthropic backend + deterministic mock
  report.py     markdown report
  cli.py        subcommands
```
