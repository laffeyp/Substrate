# SWE-bench External SDK Bridge Mapping

> **Purpose.** SDD-kit discipline: before any sprint writes code that imports `swebench`, document the
> *actual* API surface so workers bind to real symbols, not invented ones. Everything below is quoted or
> derived from the real `princeton-nlp/SWE-bench` source (the `swebench` PyPI package) and the Hugging Face
> dataset cards, not from blog summaries. Verbatim signatures are marked **[verbatim]**; inferred/derived
> notes are marked **[derived]**. Version pin: **`swebench==4.1.0`** (latest on PyPI as of 2026-06; package
> summary: "The official SWE-bench package"). Confirm the pin before the sprint — see §6.

---

## 1. The real API surface

### 1.1 Entrypoint — `swebench.harness.run_evaluation`

Run as a module CLI (`python -m swebench.harness.run_evaluation ...`) or call `main()` directly.

**[verbatim]** `main()` signature (`swebench/harness/run_evaluation.py`):

```python
def main(
    dataset_name: str,
    split: str,
    instance_ids: list,
    predictions_path: str,
    max_workers: int,
    force_rebuild: bool,
    cache_level: str,
    clean: bool,
    open_file_limit: int,
    run_id: str,
    timeout: int,
    namespace: str | None,
    rewrite_reports: bool,
    modal: bool,
    instance_image_tag: str = "latest",
    env_image_tag: str = "latest",
    report_dir: str = ".",
):
```

**[verbatim]** Key argparse defaults:

| Arg | Default | Notes |
|---|---|---|
| `dataset_name` | `"SWE-bench/SWE-bench_Lite"` | HF dataset name **or** path to a local JSON file |
| `split` | `"test"` | |
| `predictions_path` | *(required)* | Path to predictions JSON/JSONL; literal `"gold"` runs the gold patches |
| `max_workers` | `4` | help: "should be <= 75% of CPU cores" |
| `run_id` | *(required)* | identifies the run; namespaces the log/report dirs |
| `timeout` | `1800` | per-instance test timeout, seconds |
| `namespace` | `"swebench"` | image registry namespace; `"none"`/`None` → build/use local images |
| `cache_level` | `"env"` | which image layers to keep (`none`/`base`/`env`/`instance`) |
| `clean` | `False` | remove images above cache level |
| `instance_image_tag` | `"latest"` | |
| `env_image_tag` | `"latest"` | |

> **Note the namespace default skew.** The CLI default is `"swebench"` (pull prebuilt images from Docker
> Hub). But the lower-level `make_test_spec()` / `get_test_specs_from_dataset()` default `namespace=None`
> (treat images as local). If our Adapter calls the low-level API directly, it must pass `namespace`
> explicitly or it will look for local images and fail to pull. **[verbatim from both files]**

### 1.2 Prediction loading **[verbatim]**

```python
predictions = get_predictions_from_file(predictions_path, dataset_name, split)
predictions = {pred[KEY_INSTANCE_ID]: pred for pred in predictions}
```

So predictions are keyed by `instance_id` after load; a duplicate `instance_id` silently overwrites.

### 1.3 Constant keys **[verbatim]** (`swebench/harness/constants/__init__.py`)

```python
KEY_INSTANCE_ID = "instance_id"
KEY_MODEL       = "model_name_or_path"
KEY_PREDICTION  = "model_patch"

FAIL_TO_PASS = "FAIL_TO_PASS"
PASS_TO_PASS = "PASS_TO_PASS"
FAIL_TO_FAIL = "FAIL_TO_FAIL"
PASS_TO_FAIL = "PASS_TO_FAIL"

class ResolvedStatus(Enum):
    NO      = "RESOLVED_NO"
    PARTIAL = "RESOLVED_PARTIAL"
    FULL    = "RESOLVED_FULL"
```

### 1.4 Instance fields read by `make_test_spec()` **[verbatim list]**

From the dataset instance dict the harness reads:
`instance_id`, `repo`, `version`, `base_commit`, `problem_statement`, `test_patch`,
`PASS_TO_PASS`, `FAIL_TO_PASS` (the last two parsed via `_from_json_or_obj` — they may be JSON-encoded
strings or already lists). `environment_setup_commit` exists as a dataset column but is consumed through
the version→spec mapping, not read by name in `make_test_spec`. **[derived]**

---

## 2. Our-Adapter-needs ↔ swebench-provides

| Our Adapter needs | swebench provides | Real symbol / path |
|---|---|---|
| Run eval on a batch of predictions | `main(...)` / module CLI | `swebench.harness.run_evaluation:main` |
| Identify an instance | `instance_id` field | `KEY_INSTANCE_ID = "instance_id"` |
| Tell harness which model | `model_name_or_path` field | `KEY_MODEL = "model_name_or_path"` |
| Submit the agent's diff | `model_patch` field (unified diff text) | `KEY_PREDICTION = "model_patch"` |
| Pick a benchmark | `dataset_name` + `split` | HF name or local JSON path |
| Subset of tasks | `instance_ids: list` | arg to `main()` |
| Parallelism | `max_workers: int` | arg to `main()` |
| Isolate a run | `run_id: str` | namespaces logs + report file |
| Read pass/fail per test | `tests_status` block in per-instance report | `report.json` (see §4) |
| Read "did we fix it" | `resolved: bool` | per-instance `report.json` |
| Aggregate score | `make_run_report` summary | `swebench.harness.reporting:make_run_report` |
| Use prebuilt images | `namespace="swebench"` | Docker Hub (see §5) |

---

## 3. The prediction we must emit

One JSON object per attempt. **Exact field names (do not invent):**

```json
{
  "instance_id": "astropy__astropy-12907",
  "model_name_or_path": "substrate-coding-flow-v1",
  "model_patch": "diff --git a/... b/...\n--- a/...\n+++ b/...\n@@ ... @@\n ..."
}
```

- `model_patch` is a **unified git diff as a string** (what `git diff` emits), applied at `base_commit`.
- File format: a JSON **array** of these objects, or a **JSONL** file (one object per line) — the loader
  handles a file path either way. **[derived from `get_predictions_from_file`]**
- `model_name_or_path` drives the report filename and the per-instance log dir; keep it stable and
  filesystem-safe (the harness does `.replace("/", "__")`).
- An empty/`None` `model_patch` is counted as an `empty_patch_instance` (not an error). **[derived]**

---

## 4. The report we must read to get "resolved"

### 4.1 Per-instance report **[verbatim]**

Written to:

```
<report_dir or logs/run_evaluation>/<run_id>/<model_name_or_path>/<instance_id>/report.json
```

The report dict (keyed at top level by `instance_id`):

```python
{
  "<instance_id>": {
    "patch_is_None": bool,
    "patch_exists": bool,
    "patch_successfully_applied": bool,
    "resolved": bool,
    "tests_status": {
      "FAIL_TO_PASS": {"success": [...], "failure": [...]},
      "PASS_TO_PASS": {"success": [...], "failure": [...]},
      "FAIL_TO_FAIL": {"success": [...], "failure": [...]},
      "PASS_TO_FAIL": {"success": [...], "failure": [...]}
    }
  }
}
```

**`resolved` is the field the Adapter keys on.** **[verbatim]** Resolution logic
(`get_resolution_status`): `resolved == True` **iff** status is `ResolvedStatus.FULL`, which requires
**FAIL_TO_PASS rate == 1.0 AND PASS_TO_PASS rate == 1.0** (every previously-failing test now passes AND no
previously-passing test regressed). Partial fixes (`0 < FAIL_TO_PASS < 1`, `PASS_TO_PASS == 1`) → `PARTIAL`
→ `resolved == False`. So a partial fix scores **zero** on this benchmark. **[verbatim]**

### 4.2 Final run report **[verbatim]** (`swebench/harness/reporting.py:make_run_report`)

Written to a file named:

```python
f"{model_name_or_path.replace('/', '__')}.{run_id}.json"
```

Structure:

```python
{
  "total_instances": int,        # size of full_dataset
  "submitted_instances": int,    # len(predictions)
  "completed_instances": int,
  "resolved_instances": int,
  "unresolved_instances": int,
  "empty_patch_instances": int,
  "error_instances": int,
  "completed_ids": [...],
  "incomplete_ids": [...],
  "empty_patch_ids": [...],
  "submitted_ids": [...],
  "resolved_ids": [...],
  "unresolved_ids": [...],
  "error_ids": [...],
  "schema_version": 2
  # when a docker client is passed, also:
  # "unstopped_instances", "unstopped_containers", "unremoved_images"
}
```

> **`schema_version: 2`** — assert this in the Adapter so a future harness schema bump fails loudly
> instead of being silently mis-parsed.
>
> The headline metric (resolve rate) = `resolved_instances / total_instances`.

---

## 5. Execution / Docker requirements

- **Docker is mandatory.** Each instance runs in a container; the harness builds a 3-layer image stack
  (`base` → `env` → `instance`). `main()` arg `cache_level` controls which layers persist.
- **Image naming [verbatim]** (`swebench/harness/test_spec/test_spec.py`):

  ```python
  # instance image
  key = f"sweb.eval.{self.arch}.{self.instance_id.lower()}:{self.instance_image_tag}"
  if self.is_remote_image:                       # is_remote_image == (namespace is not None)
      key = f"{self.namespace}/{key}".replace("__", "_1776_")

  # env image:  f"sweb.env.{MAP_REPO_TO_EXT[repo]}.{arch}.{val}:{env_image_tag}"
  # base image: f"sweb.base.{MAP_REPO_TO_EXT[repo]}.{arch}:{base_image_tag}"
  ```

  - **`arch`** is `x86_64` or `arm64` — image tags are arch-specific; an arm64 host (Apple Silicon) pulls
    different images than x86_64, and **not all instances have prebuilt arm64 images** (common failure
    mode → emulation or rebuild).
  - **`__` → `_1776_`** rewrite: Docker tags can't contain `__`, and `instance_id`s do
    (`owner__repo-PR`). So the on-registry name of `astropy__astropy-12907` is
    `swebench/sweb.eval.x86_64.astropy_1776_astropy-12907:latest`. **Do not** construct image names by hand
    in the Adapter — go through `TestSpec`, or you'll get the `__`/casing wrong.
  - **Default namespace `"swebench"`** → images pulled from **Docker Hub** `docker.io/swebench/...`.
    (Some leaderboard tooling / forks mirror to `ghcr.io`; for the stock package the namespace is the bare
    Docker Hub org `swebench`.) **[derived — registry host is Docker's default for a bare namespace]**
- **Resources:** prebuilt instance images are large; a full `SWE-bench_Verified` (500 instances) run pulls
  tens-to-hundreds of GB and is disk-bound. Keep `max_workers <= ~75% of cores`; mind `open_file_limit`
  (arg exists for ulimit bumps). Budget disk + use `cache_level`/`clean` to evict. **[derived from args +
  known harness behavior]**

### 5.1 Datasets (where instance fields live)

| Dataset (HF) | Split | Size | Notes |
|---|---|---|---|
| `princeton-nlp/SWE-bench_Verified` | `test` | **500** | Human-filtered; the standard target. Columns: `instance_id, repo, base_commit, patch, test_patch, problem_statement, hints_text, created_at, version, environment_setup_commit, FAIL_TO_PASS, PASS_TO_PASS`. `FAIL_TO_PASS`/`PASS_TO_PASS` are **JSON-string-encoded lists**. **[verbatim from HF card]** |
| `SWE-bench/SWE-bench_Lite` | `test` | 300 | CLI default `dataset_name`. |
| `SWE-bench/SWE-bench` | `test` | ~2.3k | Full set. |

### 5.2 SWE-bench-Live (contamination control) **[mostly verbatim from HF card + paper 2505.23419]**

A **separate** dataset+harness line for recency/contamination control:

- HF dataset: **`SWE-bench-Live/SWE-bench-Live`**.
- Splits: `lite` (300, frozen), `verified` (500, frozen), `test` (1000), `full` (1890, "latest issues").
- **Recency window:** issues created **2024-01-01 → 2025-04-20**; **+50 new verified instances/month** via
  an automated curation pipeline → contamination-resistant moving target.
- Columns mirror SWE-bench (`instance_id, repo, base_commit, FAIL_TO_PASS, PASS_TO_PASS, patch,
  test_patch, problem_statement, ...`) **plus** `test_cmds`, `log_parser`, `difficulty`, **`image_key`**
  (instance carries its own image reference), `pull_number`, `created_at`.
- **Harness/images differ.** SWE-bench-Live ships its **own** evaluation harness and its **own** image set
  (instance-level images referenced by the `image_key` column), *not* the stock `swebench/...` Docker Hub
  namespace. **Treat it as a distinct backend in the Adapter** — same prediction format and same
  `resolved`-style scoring, but a different runner/registry. **[derived — see Open Questions §6]**

---

## 6. Open questions / version-skew flags

1. **Pin `swebench` and re-verify before the sprint.** This map is against **4.1.0** / `main`. The harness
   API has churned across major versions (the `namespace`/`modal`/`instance_image_tag` args and
   `schema_version: 2` are recent). Lock the version in `pyproject`/lockfile; if it drifts, re-run this
   reverse-engineering. **Confirmed unverified across versions:** the exact `main()` arg list for the
   *pinned* wheel — read it from the installed package, not just `main` on GitHub.
2. **Repo moved.** Package homepage now points to `github.com/swe-bench/SWE-bench` (org rename from
   `princeton-nlp`); HF dataset names appear under both `princeton-nlp/...` and `SWE-bench/...`. Old
   `princeton-nlp/...` names still resolve but verify the canonical name for the dataset you target.
3. **`get_predictions_from_file` exact accepted formats** (JSON array vs JSONL vs dict-of-dicts) and
   whether it tolerates extra prediction fields — confirm by reading the function in the pinned wheel
   before emitting predictions. Marked [derived] above.
4. **Registry host for `namespace="swebench"`.** Verified the namespace *string* is `swebench` from source;
   that it resolves to `docker.io/swebench` is Docker default-registry behavior, not an explicit constant.
   Confirm the first time we pull. `ghcr.io` mirrors exist for some forks/leaderboards.
5. **arm64 image coverage.** On Apple Silicon dev machines, confirm prebuilt `arm64` images exist for the
   target instances; otherwise plan for x86_64 emulation or local rebuild (slow).
6. **SWE-bench-Live harness module path** could not be pulled from its HF card here. Before building the
   Live backend, locate its harness repo (the paper is arXiv 2505.23419, "SWE-bench Goes Live!") and
   confirm whether it subclasses `swebench.harness.run_evaluation` or ships a standalone runner, and the
   exact `image_key`/registry it uses.
7. **`environment_setup_commit`** is a dataset column but isn't read by name in `make_test_spec`; setup is
   keyed off `version` via internal maps. Don't rely on passing it through predictions.

---

## 7. Sources

All retrieved 2026-06 (raw source on `main` unless noted):

- `run_evaluation.py` (entrypoint, args, prediction load):
  https://raw.githubusercontent.com/princeton-nlp/SWE-bench/main/swebench/harness/run_evaluation.py
- `constants/__init__.py` (KEY_* , FAIL_TO_PASS/PASS_TO_PASS, ResolvedStatus):
  https://raw.githubusercontent.com/princeton-nlp/SWE-bench/main/swebench/harness/constants/__init__.py
- `grading.py` (per-instance report dict, `resolved` logic):
  https://raw.githubusercontent.com/princeton-nlp/SWE-bench/main/swebench/harness/grading.py
- `reporting.py` (`make_run_report`, final report schema + filename):
  https://raw.githubusercontent.com/princeton-nlp/SWE-bench/main/swebench/harness/reporting.py
- `test_spec/test_spec.py` (image-key f-strings, `is_remote_image`, `__`→`_1776_`):
  https://raw.githubusercontent.com/princeton-nlp/SWE-bench/main/swebench/harness/test_spec/test_spec.py
- `docker_build.py` (image build flow, TestSpec usage):
  https://raw.githubusercontent.com/princeton-nlp/SWE-bench/main/swebench/harness/docker_build.py
- PyPI release/version metadata (`4.1.0`, homepage, repo rename):
  https://pypi.org/pypi/swebench/json
- HF dataset card — SWE-bench_Verified (columns, 500 rows, JSON-encoded test lists):
  https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified
- HF dataset card — SWE-bench-Live (splits, recency window, extra columns):
  https://huggingface.co/datasets/SWE-bench-Live/SWE-bench-Live
- SWE-bench-Live paper ("SWE-bench Goes Live!", recency/contamination, monthly +50):
  https://arxiv.org/pdf/2505.23419

## Containerization — REQUIRED for this path (decision 2026-06-26)

SWE-bench runs every instance in its OWN container BY DESIGN (untrusted patches against a real repo +
reproducibility); `assay/swebench.py` already lazy-imports swebench and runs Docker via TestSpec. So
containerization is not bolt-on here — it is the substrate this path assumes from the start.

It wraps the GRADE (running candidate/patch code), NEVER the models (Ollama is a separate server, so it
does not slow inference). It is the right answer to the broad untrusted-execution exposure we currently
run on the bare host with only a timer: resource bombs (cgroup limits), network exfil (`--network none`),
filesystem reads/writes of the host (FS isolation). For our OWN bank, the seam is a sandboxed
`coding_flow.gate.run_gate` mode (container or bwrap/nsjail). The specific test-file-READING hole is
fixed cheaper by an input/output split (feed inputs, compare expected in the grader, never on disk the
candidate reads) — not by a container. NOT needed for the current weak-local-model runs; add at the
SWE-bench step, after the current benchmarking work is finished.
