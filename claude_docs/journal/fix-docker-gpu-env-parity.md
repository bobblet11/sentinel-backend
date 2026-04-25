---
## [2026-04-01] Fix Merge Conflict Reversion of PyTorch cu124 Wheel Index in GPU Dockerfile

**Date**: April 1, 2026 (exact time not recorded)
**Agent**: `claude-inline`
**Branch**: `newretrieval-fixes`
**Triggered By**: Post-merge inspection revealed the conflict resolution during `merge: integrate origin/newretrieval-fixes into refactor/nlp` (commit 2963cbe) incorrectly kept the remote side's `cu121` wheel index, undoing the intentional `cu124` upgrade.

### Summary
Restored `--index-url https://download.pytorch.org/whl/cu124` in the GPU Dockerfile after a bad merge conflict resolution reverted it to `cu121`. PyTorch 2.6.0 publishes no `cu121` wheels, so the erroneous index-url would have caused `docker build` to fail immediately at the `pip install torch==2.6.0` step. The base image is already `nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04`, so the wheel index and base image are now consistent again.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `docker/base/GPU_ML_base/Dockerfile` | Modified | Reverted bad merge: changed `--index-url https://download.pytorch.org/whl/cu121` back to `--index-url https://download.pytorch.org/whl/cu124` |

### Details
- Root cause: the merge commit 2963cbe resolved a conflict by choosing the remote (`origin/newretrieval-fixes`) version of the `pip install` line, which still referenced `cu121`. The local branch had already corrected this to `cu124` as part of the CUDA 12.4 upgrade.
- PyTorch 2.6.0 has no published wheels for `cu121`. Leaving the wrong index-url would produce a "no matching distribution found" error at build time — a silent build-time failure, not a runtime regression.
- The base NVIDIA image (`nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04`) was not changed; only the pip index-url was corrected.
- No stream schemas, Pydantic models, DB models, or service logic were touched.

### Pipeline Impact
NLP GPU build path only. Without this fix, `docker build` for `sentinel/python-ml-gpu:3.12-cuda124` would fail before any container ever starts, blocking all GPU-mode NLP processing. CPU path and all other services are unaffected.

---
## [2026-04-01] Upgrade GPU Docker Base Image to CUDA 12.4 and Align Dependency Versions with sentinel-env

**Date**: April 1, 2026 (exact time not recorded)
**Agent**: `claude-inline`
**Branch**: `newretrieval-fixes`
**Triggered By**: Environment parity gap between Docker GPU image (CUDA 12.1, torch 2.5.1, numpy 1.26.4, pandas 2.2.2) and the sentinel-env conda environment (CUDA 12.4, torch 2.6.0, numpy 2.4.3, pandas 3.0.1) was causing unreliable local-vs-Docker test comparisons.

### Summary
Updated the GPU NLP Docker base image from CUDA 12.1 to CUDA 12.4 using the correct NVIDIA image tag (`nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04`, without a version suffix after `cudnn`). PyTorch and its companions were bumped to 2.6.0+cu124, and numpy and pandas were updated to match the sentinel-env conda pinned versions. A previous revert commit (2645e5e) used a non-existent tag; this change uses the verified correct tag.

### Files Changed
| File Path | Change Type | Description |
|-----------|-------------|-------------|
| `docker/base/GPU_ML_base/Dockerfile` | Modified | Base image changed from `nvidia/cuda:12.1.1-cudnn8-devel-ubuntu22.04` to `nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04`; PyTorch updated from `2.5.1+cu121` to `2.6.0+cu124`, torchvision `0.20.1` to `0.21.0`, torchaudio `2.5.1` to `2.6.0`, index-url changed from `cu121` to `cu124` |
| `docker/base/core-requirements.txt` | Modified | Pinned `numpy==1.26.4` bumped to `numpy==2.4.3`; pinned `pandas==2.2.2` bumped to `pandas==3.0.1` |
| `docker/base/core-nlp-requirements.txt` | Modified | numpy lower bound updated from `>=1.26.4` to `>=2.4.3` |
| `docker/compose/docker-compose.yml` | Modified | NLP GPU service base image tag updated from `sentinel/python-ml-gpu:3.12-cuda121` to `sentinel/python-ml-gpu:3.12-cuda124` |
| `scripts/deploy.sh` | Modified | GPU base image build tag updated from `sentinel/python-ml-gpu:3.12-cuda121` to `sentinel/python-ml-gpu:3.12-cuda124` |
| `configs/.env.template` | Modified | Comment example updated from `cuda121` to `cuda124` |

### Details
- The NVIDIA image tag convention changed between CUDA 12.1 and 12.4: the 12.1 tag included a versioned cuDNN suffix (`cudnn8`), while the 12.4 tag omits the version number (`cudnn` only). An earlier attempt (reverted in commit 2645e5e) used the wrong tag pattern and would have failed at build time.
- numpy 2.x and pandas 3.x both contain breaking API changes relative to their 1.x/2.x predecessors, meaning tests passing locally against sentinel-env but failing in Docker (or vice versa) could silently mask real regressions.
- The CPU build path (`python-ml-cpu`) is unaffected — no changes were made to the CPU Dockerfile or its requirements.
- A full rebuild of the `sentinel/python-ml-gpu:3.12-cuda124` base image is required before the NLP GPU service can be deployed.
- Consumers of this base image: the NLP microservice GPU variant only. No other service uses the GPU image.
- No stream schemas, Pydantic models, or DB models were changed.

### Pipeline Impact
NLP (GPU path only). The CUDA and PyTorch version change affects the entire GPU build chain. Any model inference code that calls PyTorch ops will run on the new runtime after rebuild. CPU path is unaffected. E2E stability on the GPU path cannot be confirmed until the base image is rebuilt and the NLP container is restarted.

---
