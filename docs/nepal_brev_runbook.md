# Nepal Aurora 1.5 — Brev Handoff Runbook

**Project**: 002-nepal-eval
**Version**: v1.1
**Purpose**: Instructions for handing off a user-provisioned Brev A100 instance
to Claude Code for P3 environment validation and inference execution.

---

## 1. Instance Creation (User Responsibility)

Create the A100 80GB instance manually through the **NVIDIA Brev Console**.

Requirements:
- GPU: NVIDIA A100 80GB
- On-demand (NOT spot)
- Region: any (Hyperstack Montreal preferred)
- conda environment `aurora_env` with Earth2Studio 0.17.0

**Claude Code does NOT provision, start, stop, delete, or otherwise manage
Brev instances.** Instance lifecycle is entirely user-managed.

---

## 2. Information to Provide After Instance Creation

Once the instance is Running, provide Claude Code with:

| Item | Example | Required? |
|------|---------|-----------|
| **Brev instance name** | `steep-emerald-tern` | YES |
| **Instance status** | Running | YES |

That is the minimum. Claude Code will discover GPU, VRAM, CUDA, conda, and repo
state automatically after connecting.

An IP address is NOT required unless the normal Brev CLI connection fails.

---

## 3. Connection Workflow (Brev CLI)

Claude Code connects via the Brev CLI, not raw SSH:

```bash
brev refresh                          # sync CLI with console-created instances
brev ls                               # confirm instance is visible and Running
brev shell <instance-name>            # SSH into instance
```

If `brev shell` fails, Claude Code will ask for the SSH IP as a fallback.

---

## 4. What Claude Code Will Do on First Connection

### Step 1: Verify repo and branch

Working directory: `/home/ubuntu/workspace/nepal-forecast-eval`

If the repo is not present, clone and checkout:
```bash
cd /home/ubuntu/workspace
git clone https://github.com/JiayanLim/nepal-forecast-eval.git
cd nepal-forecast-eval
git checkout feature/nepal-inference
```

Before doing anything else, verify:
```bash
git remote -v          # origin = JiayanLim/nepal-forecast-eval
git log --oneline -1   # confirm expected commit SHA
git branch             # confirm feature/nepal-inference
```

### Step 2: Report instance info

Claude Code reports:
- Instance name
- GPU model and VRAM (`nvidia-smi`)
- CUDA version, NVIDIA driver version
- Hostname
- Working directory
- Git commit SHA, branch, remote

### Step 3: Verify environment

```bash
conda activate aurora_env
python -c "import sys; print(f'Python {sys.version}')"
python -c "import earth2studio; print(f'E2S {earth2studio.__version__}')"
python -c "import torch; print(f'torch={torch.__version__}, cuda={torch.version.cuda}, gpu={torch.cuda.get_device_name(0)}, vram={torch.cuda.get_device_properties(0).total_mem/1e9:.1f}GB')"
```

Verify:
- `aurora_env` exists and activates
- Python version
- `earth2studio.__version__ == 0.17.0`
- PyTorch version
- CUDA available
- A100 80GB visible
- `Aurora1p5` imports
- `Aurora1p5.load_default_package()` loads checkpoint
- `verify_patch()` returns `True`

### Step 4: Verify ERA5T IC files

Check whether the P2 ERA5T IC files are available on the instance:
```bash
ls results/nepal/era5_ic/*.nc | wc -l    # expect 14
```

If IC files are NOT present: **STOP** and report exactly what is missing.
Do NOT silently fetch a different dataset or substitute data.

Note: The inference script (`nepal_inference.py`) uses `earth2studio.data.ARCO()`
which fetches IC from ARCO at inference time (same as Myanmar workflow). The P2
IC files serve as provenance/validation — E2S handles the actual IC fetch.

### Step 5: Run environment check + 2-step smoke test

```bash
cd /home/ubuntu/workspace/nepal-forecast-eval
python scripts/nepal_brev_check.py
```

This runs all validation checks including a 2-step Nepal bbox smoke test.
Output: `results/nepal/validation/p3_brev_check.json`

### Step 6: STOP and report checkpoint

Claude Code reports:
1. Instance name
2. GPU model and VRAM
3. CUDA version, PyTorch version, E2S version
4. NVIDIA driver version
5. Patch verification result
6. Checkpoint loading result
7. ERA5T IC file availability
8. Smoke test output shape and t2m range
9. Smoke test wall time
10. Any errors or warnings
11. Overall PASS/FAIL

**Claude Code will NOT proceed to full inference until the user explicitly approves.**

---

## 5. Full Inference (After User Approval Only)

Once the user explicitly approves the environment checkpoint:

```bash
# In tmux session on Brev (survives SSH disconnect)
tmux new -s nepal
cd /home/ubuntu/workspace/nepal-forecast-eval
conda activate aurora_env

# Set cache dirs (if /ephemeral exists)
export EARTH2STUDIO_CACHE=/ephemeral/.cache/earth2studio
export HF_HOME=/ephemeral/.cache/huggingface

# Run all 14 inits
python scripts/nepal_inference.py
```

The script:
- Runs 14 daily initialisations (168h each)
- E2S fetches IC from ARCO at inference time
- Extracts Nepal bbox per step
- Applies unit conversions
- Writes `results/nepal/forecasts/{slug}_aurora.nc` (atomic)
- Writes `results/nepal/provenance/{slug}_aurora_provenance.json`
- Writes `results/nepal/manifest.json`
- Resumable: skips already-valid files on re-run

Single-init mode (for debugging):
```bash
python scripts/nepal_inference.py --slug 20260720
```

Expected runtime: ~309s/init x 14 = ~72 min
Expected GPU cost: ~$7-10

---

## 6. After Inference

1. Structural validation of all 14 forecast files
2. Produce final manifest and provenance records
3. STOP for user review
4. Transfer files to local machine (user manages)
5. Shut down Brev instance (user responsibility)
6. Local validation (P4)

---

## 7. Safety Rules

- Do NOT compute any evaluation metrics
- Do NOT modify `myanmar-forecast-eval`, `myanmar-weather-forecast`, or `nepal-weather-forecast`
- Do NOT push commits unless the user explicitly authorises
- Do NOT provision, start, stop, or delete Brev instances
- Do NOT substitute or silently re-fetch datasets

---

*Runbook v1.1 — 2026-08-27.*
