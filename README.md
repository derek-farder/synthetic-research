# synthetic-research-kit

A Claude Code workspace for interviewing synthetic personas and turning the results into hypotheses, with guardrails that keep simulated output from being mistaken for research. **This repository contains no client data.** It holds the agents, skills, checker, test harness and a fictional example.

## Use it

```bash
git clone <repo-url> synthetic-research
cd synthetic-research
git config core.hooksPath .githooks     # blocks accidental commits of client data
claude
```

Claude Code reads `CLAUDE.md`, `.claude/agents/`, `.claude/skills/` and `.claude/settings.json` from the folder you start it in, so there is nothing else to install. Start it from the repo root. It may ask you to trust the folder the first time.

**Requirements**
- Claude Code, signed in with an account or deployment your firm has approved for the material you will load.
- Python 3.9+ (`python3`, or `python` on Windows).
- On Windows, run from WSL or Git Bash; the helper scripts are bash.
- Calibration only: `pip install -r requirements.txt` and `ANTHROPIC_API_KEY` in your environment. Everything else runs inside Claude Code.

**Try it first with fictional data**

```bash
scripts/load-example.sh      # copies the example nurse/biomed personas into the (gitignored) data folders
claude                       # then try /plan-study
```

It refuses to run if `evidence/evidence.json` already exists, so it cannot overwrite real material.

## Where client data goes

Wherever you clone this is where your data lives. Clone into a location your firm and the client approve for that engagement, not a personal laptop folder or a personal cloud drive.

| Committed to git | Gitignored (client data) |
|---|---|
| `CLAUDE.md`, `.claude/`, `scripts/`, `tools/`, `examples/`, `studies/_template/` | `personas/`, `evidence/`, `holdout/`, `calibration/`, `studies/<your studies>` |

Four layers stop client data reaching the repo: the `.gitignore`; the `pre-commit` hook (catches `git add -f` by anyone, but only after you enable it with the `git config` line above); a project setting that stops Claude Code running `git add -f`; and a rule in `CLAUDE.md`. None of them can stop you pasting a quote into a kit file by hand, so keep `examples/` fictional and review diffs before you push.

## Workflow

| Step | Skill | Notes |
|---|---|---|
| 1 | `/build-persona` | Real quotes into `evidence/`; every persona claim cites them. |
| 2 | `/calibrate-persona` | Backtest against held-out interviews plus coherence probes; writes `calibration/<id>/STATUS.md`. |
| 3 | `/plan-study` | Neutral discussion guide, then stops for your approval. |
| 4 | `/run-interview` | Runs the approved guide through the `persona-runner` subagent; saves tagged transcripts. |
| 5 | `/synthesize-study` | Hypotheses with support counts, `skeptic` review, then `python3 scripts/check_study.py studies/<study>`. |

`scripts/check_study.py` fails a study whose quotes are untagged, whose hypotheses lack `[support: N runs / M personas]`, or whose calibration disclosure is missing or wrong (a persona edited after calibration reads as `stale`).

## Updating and contributing

- `git pull` updates the kit and never touches your data folders.
- Improve skills or agents on a branch and open a pull request. Check the diff for client details before pushing.
- If you change `.claude/agents/persona-runner.md`, mirror the rules in `tools/persona-lab/persona_lab/runner.py`, otherwise calibration describes a different pipeline than the one you interview.

## Sharing results

Share the synthesis as a document in the engagement's approved channel, not as a hosted page. Keep the `[SYN: ...]` tags, the calibration lines and the "hypotheses, not findings" framing in the exported copy, and run the checker before exporting. The tags are what stop a simulated quote being read as a participant's.

## Caveats

- The agents and skills have been loaded by Claude Code but not yet run through a full study. Expect to tweak wording after your first one.
- Some controls are instructions, not walls. The blind-interview rule and "don't read the holdout" depend on the model following them; the `Read` deny on `holdout/` does not stop shell commands.
- Interviews cost one subagent call per question per run. Three personas x three runs x eight questions is 72 calls before follow-ups.
- Real interview transcripts may have been collected under consent that covers research, not AI processing. Check before loading them.
- `calibrated` means a persona did not visibly fail against the holdout you had. It does not mean valid.
- `tools/persona-lab` has its own README with test details, thresholds and limits.
