#!/usr/bin/env bash
# Copy the FICTIONAL example persona, evidence, holdout, probes and study into the live
# (gitignored) folders so you can try the workflow. Refuses to touch a workspace that
# already holds evidence, so it can never overwrite real client material.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -e evidence/evidence.json ]; then
  echo "evidence/evidence.json already exists. Not overwriting. Use a fresh clone to try the example." >&2
  exit 1
fi
cp examples/personas/*.md personas/
cp examples/evidence.json evidence/evidence.json
cp examples/holdout/*.json holdout/
mkdir -p calibration/probes && cp examples/probes/*.json calibration/probes/
cp -r examples/studies/example-pump-onboarding studies/
echo "Loaded the fictional example (personas dana and marcus). These files are gitignored."
echo "Next: run 'claude' here, then try /plan-study. Replace the example with real evidence via /build-persona."
