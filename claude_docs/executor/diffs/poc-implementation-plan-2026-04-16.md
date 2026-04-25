# Diffs: poc-implementation-plan — 2026-04-16

All files are newly created (no prior state). Diffs show full content additions.

---

### Diff: scripts/topic_clustering/__init__.py — Task 1
```
--- /dev/null
+++ scripts/topic_clustering/__init__.py
@@ (new file) @@
+(empty file — package marker)
```

---

### Diff: scripts/topic_clustering/requirements.txt — Task 2
```
--- /dev/null
+++ scripts/topic_clustering/requirements.txt
@@ (new file) @@
+bertopic>=0.16
+umap-learn>=0.5.5
+hdbscan>=0.8.33
+sentence-transformers>=2.2.0
+psycopg2-binary>=2.9
+sqlalchemy>=2.0
+pgvector>=0.2.0
+python-dotenv>=1.0
+numpy>=1.24
+pandas>=2.0
```

---

### Diff: scripts/topic_clustering/poc_cluster.py — Task 3
```
--- /dev/null
+++ scripts/topic_clustering/poc_cluster.py
@@ (new file — 330 lines) @@
+Key functions: load_env, get_engine, fetch_articles_with_embeddings,
+  run_zero_shot_bertopic, build_results, print_quality_summary,
+  save_results, save_topic_info, _build_docs, main
+
+PREDEFINED_TOPICS = ["Politics","World","Technology","Health",
+                      "Science","Business","Entertainment","Sports"]
+
+SQL uses: SELECT ... AVG(c.decontextualised_embedding)::vector(768) ...
+          WHERE c.decontextualised_embedding IS NOT NULL
+          GROUP BY a.id HAVING COUNT(c.id) > 0
+
+Embedding parsing handles both string '[0.1,...]' and list/array forms.
+Early exit if < 10 articles found.
+argparse CLI with --env-file, --output-dir, --min-topic-size,
+  --seed, --zeroshot-threshold, --use-title-only
```

---

### Diff: scripts/topic_clustering/test_quality.py — Task 4
```
--- /dev/null
+++ scripts/topic_clustering/test_quality.py
@@ (new file — 210 lines) @@
+Checks: confidence_distribution, topic_coverage, outlier_ratio,
+        discovered_topics_sanity, spot_check_titles
+Exits 0 if all pass, 1 if any fail.
```

---

### Diff: scripts/topic_clustering/test_consistency.py — Task 5
```
--- /dev/null
+++ scripts/topic_clustering/test_consistency.py
@@ (new file — 160 lines) @@
+Checks: same-seed determinism (expects 100% agreement),
+        cross-seed agreement seed=42 vs seed=99 (warns if <80%, no hard fail).
+Imports: fetch_articles_with_embeddings, run_zero_shot_bertopic from poc_cluster.
```

---

### Diff: scripts/topic_clustering/test_edge_cases.py — Task 6
```
--- /dev/null
+++ scripts/topic_clustering/test_edge_cases.py
@@ (new file — 240 lines) @@
+Tests: test_no_claims_excluded, test_single_claim_articles,
+       test_null_embeddings_excluded, test_empty_corpus_handling,
+       test_short_text_handling
+Imports: fetch_articles_with_embeddings, run_zero_shot_bertopic from poc_cluster.
+Uses unittest.mock to simulate empty corpus without real DB call.
+Exits 1 if any test fails.
```
