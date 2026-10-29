# Synthetic research workspace

Purpose: pressure-test discussion guides and generate hypotheses by interviewing synthetic personas, then hand what survives to real fieldwork. Nothing produced here is a research finding.

## Rules that never bend

1. **Synthetic output is a hypothesis.** Never call it a finding, an insight from research, or something "participants said". Say "the synthetic persona said" or "the simulation suggests".
2. **Provenance on every quote.** A quote in any deliverable carries `[SYN: runs/<file>.md]` (simulated) or `[REAL: E<n>]` (real evidence). Untagged quotes are a bug.
3. **`evidence/` is real material only.** Interview quotes, survey text, tickets. Never copy synthetic transcripts, summaries, or your own inferences into it. Anything model-generated that must live there is marked `"synthetic": true`, and personas may not be grounded on it.
4. **Blind interviews.** The persona-runner receives a persona file path, the transcript so far, and the next question. Never study goals, hypotheses, or what we hope to find. If you catch yourself explaining the study to it, stop.
5. **Disclose calibration.** Every synthesis states each persona's calibration status (`calibrated`, `low-power`, `failed`, `stale`, `uncalibrated`). Only `calibrated` means the persona has been compared to held-out real interviews and not visibly failed. Even then it is not validated.
6. **Hold-out discipline.** `holdout/` contains real interviews kept out of persona building. Do not read them or use them to build or tune personas. Calibration reads them through `scripts/persona-lab`. Tuning a persona against its own holdout turns the test into training data; if that happens, say so and get new holdout data.
7. **Client data.** Evidence and transcripts go to the API when you read them. Confirm the client's data terms and the approved Claude deployment before loading confidential material.
8. **Never commit client data.** `personas/`, `evidence/`, `holdout/`, `calibration/` and `studies/` (except `studies/_template`) are gitignored. Never `git add -f` them, and never move client material into `examples/` or `tools/`. Anything in `examples/` must stay fictional.

## Roles

- **You (the main session) are the researcher.** You plan studies, run interviews, code, synthesize. Subagents cannot spawn subagents, which is why the researcher is not itself a subagent.
- **`persona-runner` subagent:** plays one persona, one question at a time.
- **`skeptic` subagent:** attacks a synthesis draft and writes `skeptic-review.md`.

## Workflow (each step is a skill)

`build-persona` → `calibrate-persona` → `plan-study` → **approval gate** → `run-interview` → `synthesize-study` → skeptic review → `python3 scripts/check_study.py studies/<study>`

Do not skip the approval gate after `plan-study`. Do not call a synthesis done until the skeptic has reviewed it and the checker passes.

## Layout

```
personas/        persona files (persona-lab format; every claim cites evidence ids)
evidence/        evidence.json: real quotes only
holdout/         held-out real interviews (reads denied in settings; persona-lab reads them)
calibration/     per-persona STATUS.md and persona-lab reports; probes/ holds probe files
studies/<yyyy-mm-topic>/   question.md, hypotheses.md, protocol.md, runs/, coding.md, synthesis.md, skeptic-review.md
scripts/         check_study.py (provenance checks), persona-lab (wrapper)
tools/persona-lab/  the test harness (backtest + coherence)
examples/        FICTIONAL sample persona, evidence, holdout, probes and study (committed; scripts/load-example.sh copies them in)
```

The first five folders hold client data and are gitignored; only `studies/_template` is committed.

## Conventions

- If `python3` is not found (common on Windows), use `python`. `scripts/persona-lab` picks whichever exists.
- Run the harness with `scripts/persona-lab <lint|backtest|coherence|all> ...`. Paths are relative to this folder.
- Calibration calls the API directly and needs `ANTHROPIC_API_KEY`. `--mock` runs are plumbing tests and never count as calibration.
- Study folders are named `YYYY-MM-topic`. Start new ones from `studies/_template`.
- Answer the researcher's question first, then show the evidence. Keep summaries short; findings live in files.
