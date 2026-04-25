# Diffs: nlp-container-fix-plan — 2026-03-31

---

### Diff: docker/base/GPU_ML_base/Dockerfile — Task 1 (cmake)

```
--- original
+++ modified
@@ line 11 @@
-    software-properties-common ca-certificates curl gnupg build-essential unzip && \
+    software-properties-common ca-certificates curl gnupg build-essential cmake unzip && \
```

---

### Diff: docker/base/GPU_ML_base/Dockerfile — Task 1 (torch pin)

```
--- original
+++ modified
@@ line 27 @@
-    torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
+    "torch>=2.6.0" "torchvision>=0.21.0" "torchaudio>=2.6.0" --index-url https://download.pytorch.org/whl/cu121
```

---

### Diff: docker/base/CPU_ML_base/Dockerfile — Task 2

```
--- original
+++ modified
@@ line 7 @@
-    torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
+    "torch>=2.6.0" "torchvision>=0.21.0" "torchaudio>=2.6.0" --index-url https://download.pytorch.org/whl/cpu
```

---

### Diff: docker/base/core-nlp-requirements.txt — Task 3 (comment update)

```
--- original
+++ modified
@@ line 2 @@
-# torch>=2.5.1 is done via wget
+# torch>=2.6.0 is installed via pip in base Dockerfiles (GPU_ML_base, CPU_ML_base)
```

---

### Diff: docker/base/core-nlp-requirements.txt — Task 3 (tiktoken)

```
--- original
+++ modified
@@ line 5-6 @@
 sentencepiece>=0.1.99
+tiktoken>=0.7.0
 protobuf>=3.20.0
```
