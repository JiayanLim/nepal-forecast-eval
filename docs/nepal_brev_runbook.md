# Nepal Aurora 1.5 — Brev Handoff Runbook

**Project**: 002-nepal-eval
**Purpose**: Instructions for handing off a user-provisioned Brev A100 instance
to Claude Code for P3 environment validation and inference execution.

---

## 1. Instance Creation (User Responsibility)

Create the Brev A100 instance yourself via the **Brev web console**.

Requirements:
- GPU: NVIDIA A100 80GB
- On-demand (NOT spot)
- Region: any (Hyperstack Montreal preferred for consistency)
- conda environment `aurora_env` with Earth2Studio 0.17.0

**Claude Code does NOT create, stop, delete, or modify Brev instances.**

---

## 2. Information to Provide After Instance Creation

Once the instance is running, provide Claude Code with:

| Item | Example | Required? |
|------|---------|-----------|
| **Brev instance name** | `steep-emerald-tern` | YES |
| **Instance status** | Running | YES |
| **GPU model + VRAM** | A100 80GB | YES |
| **SSH/access method** | `brev shell` or SSH IP | YES |
| **Repo cloned on instance?** | yes/no | YES |
| **Remote working directory** | `/home/user/nepal-forecast-eval` | If cloned |
| **aurora_env exists?** | yes/no | YES |

### Preferred access: Brev CLI

If the Brev CLI is installed locally, Claude Code can connect via:

```bash
brev refresh                          # sync CLI with console-created instances
brev shell <instance-name>            # SSH into instance
```

If `brev shell` is not available, provide the SSH connection string:
```
ssh <user>@<ip-address>
```

---

## 3. What Claude Code Will Do on First Connection

### Step 1: Connect and verify basic environment
```bash
# Connect
brev shell <instance-name>

# Verify GPU
nvidia-smi

# Activate conda
conda activate aurora_env

# Verify E2S
python -c "import earth2studio; print(earth2studio.__version__)"

# Verify PyTorch/CUDA
python -c "import torch; print(f'torch={torch.__version__}, cuda={torch.version.cuda}, gpu={torch.cuda.get_device_name(0)}, vram={torch.cuda.get_device_properties(0).total_mem/1e9:.1f}GB')"
```

### Step 2: Clone repo and checkout branch (if not already done)
```bash
cd /home/user  # or /ephemeral
git clone https://github.com/JiayanLim/nepal-forecast-eval.git
cd nepal-forecast-eval
git checkout feature/nepal-inference
```

### Step 3: Verify precipitation patch
```bash
python -c "
import sys; sys.path.insert(0, '.')
from src.pipeline.inference import verify_patch
print('PATCH:', verify_patch(raise_on_fail=False))
"
```

If patch is NOT applied, fix it:
```bash
E2S_PATH=$(python -c "import earth2studio, os; print(os.path.dirname(earth2studio.__file__))")
# Edit $E2S_PATH/models/px/aurora1p5.py lines 128-129:
# Change needs_log_untransform=True to needs_log_untransform=False
# for both scaled_tp_1h and scaled_sf_1h
```

### Step 4: Run full environment check + smoke test
```bash
cd /path/to/nepal-forecast-eval
python scripts/nepal_brev_check.py
```

This runs all 8 validation checks including a 2-step Nepal bbox smoke test.
Output: `results/nepal/validation/p3_brev_check.json`

### Step 5: STOP and report checkpoint

Claude Code will report:
1. GPU model and VRAM
2. CUDA version, PyTorch version, E2S version
3. Patch verification result
4. Checkpoint loading result
5. Smoke test output shape and t2m range
6. Smoke test wall time
7. Any errors or warnings
8. Overall PASS/FAIL

**Claude Code will NOT proceed to full inference until the user explicitly approves.**

---

## 4. Full Inference (After User Approval)

Once the user approves the P3 environment checkpoint:

```bash
# In tmux session on Brev
tmux new -s nepal
cd /path/to/nepal-forecast-eval
conda activate aurora_env  # if not already active

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

## 5. After Inference

1. Verify 14/14 forecast files exist with correct shape
2. Transfer files to local machine
3. Shut down Brev instance (user responsibility)
4. Local validation (P4)

---

*Runbook v1.0 — 2026-08-27.*
