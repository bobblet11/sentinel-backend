# Execution Log: nlp-container-fix-plan

Date: 2026-03-31
Status: PARTIAL (Tasks 1-3 COMPLETED; Tasks 4-5 require Docker rebuild — out of scope for file executor)

---

## Task 1: Pin torch >= 2.6.0 in GPU Dockerfile + add cmake
- Status: COMPLETED
- Dependency Check: PASSED (no dependencies)
- Files Modified: docker/base/GPU_ML_base/Dockerfile
- old_str (apt-get line): `software-properties-common ca-certificates curl gnupg build-essential unzip`
- new_str (apt-get line): `software-properties-common ca-certificates curl gnupg build-essential cmake unzip`
- old_str (torch install): `    torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121`
- new_str (torch install): `    "torch>=2.6.0" "torchvision>=0.21.0" "torchaudio>=2.6.0" --index-url https://download.pytorch.org/whl/cu121`
- Verification: PASSED (re-read confirmed cmake on line 11, torch pins on line 27)
- Rollback Instruction: Revert cmake removal and torch unpinning in GPU Dockerfile

---

## Task 2: Pin torch >= 2.6.0 in CPU Dockerfile
- Status: COMPLETED
- Dependency Check: PASSED (no dependencies)
- Files Modified: docker/base/CPU_ML_base/Dockerfile
- old_str: `    torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu`
- new_str: `    "torch>=2.6.0" "torchvision>=0.21.0" "torchaudio>=2.6.0" --index-url https://download.pytorch.org/whl/cpu`
- Verification: PASSED (re-read confirmed torch pins on line 7)
- Rollback Instruction: Revert torch pin in CPU Dockerfile

---

## Task 3: Add tiktoken to core-nlp-requirements.txt
- Status: COMPLETED
- Dependency Check: PASSED (no dependencies)
- Files Modified: docker/base/core-nlp-requirements.txt
- old_str: `# torch>=2.5.1 is done via wget`
- new_str: `# torch>=2.6.0 is installed via pip in base Dockerfiles (GPU_ML_base, CPU_ML_base)`
- old_str: `sentencepiece>=0.1.99\nprotobuf>=3.20.0`
- new_str: `sentencepiece>=0.1.99\ntiktoken>=0.7.0\nprotobuf>=3.20.0`
- Verification: PASSED (re-read confirmed tiktoken on line 6, updated comment on line 2)
- Rollback Instruction: Remove tiktoken line and revert comment in core-nlp-requirements.txt

---

## Task 4: Rebuild and Test
- Status: PENDING (depends on Tasks 1, 2, 3)

## Task 5: Run existing tests
- Status: PENDING (depends on Task 4)
