# Quick start

## 1. Install

Use Python 3.11 or newer from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,analysis]'
pytest -q
```

M0--M2 require the Argo CLI for their direct G5 dry-run check. M5 additionally requires a working Docker installation. On macOS, the generated-code evaluator uses Seatbelt; readiness reports the available isolation mechanism.

## 2. Inspect the packaged results

```bash
shasum -a 256 -c results/paper/SHA256SUMS
python3 - <<'PY'
import json
from pathlib import Path
p = Path('results/paper/analysis/batch_validation.json')
d = json.loads(p.read_text())
print(d['primary'])
print(d['ablation'])
PY
```

The readable summary is `results/paper/analysis/report.md`. Run-level and instance-level CSV files are in the same directory.

## 3. Regenerate the paper analysis

```bash
make paper-analysis
```

The command writes a fresh bundle to `results/regenerated/evaluation_final` and leaves the packaged publication bundle unchanged.

## 4. Run a one-instance pilot

Export the token named by the selected model configuration, then run readiness and the pilot:

```bash
export DEEPINFRA_TOKEN='...'
make readiness CONFIG=experiments/config/models.deepinfra.v21.json \
  FREEZE=experiments/config/freeze.deepinfra.v21.json \
  MODEL=deepinfra-qwen3-coder-480b-turbo

make pilot CONFIG=experiments/config/models.deepinfra.v21.json \
  FREEZE=experiments/config/freeze.deepinfra.v21.json \
  MODEL=deepinfra-qwen3-coder-480b-turbo
```

Published freeze files are immutable. Use the pilot to test compatibility, but create a new candidate freeze before collecting a new study.

