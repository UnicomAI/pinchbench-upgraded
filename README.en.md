# PinchBench-Upgraded

> 🇨🇳 [中文](README.md)

Cross-platform Python tool that performs secondary processing on the upstream [PinchBench](https://pinchbench.com/) public data and produces interactive bilingual (zh/en) HTML leaderboards.

**Highlights**: binary validity check at the **single-submission** granularity → strict version management → three-tier aggregation (per-task / per-category / overall) → 7-metric self-contained HTML (success rate / cost / duration / value / time efficiency / parameters / runs) → country + open-weight filters.

Data source: [PinchBench](https://pinchbench.com/) ([MIT-licensed open source](https://github.com/pinchbench/leaderboard), led by kilo.ai). This tool never modifies any model's original submission data — it only re-validates and re-aggregates for presentation. Thanks to the PinchBench team for releasing the data.

---

## Table of Contents

1. [Installation](#1-installation)
2. [Quick Start](#2-quick-start)
3. [Command Reference](#3-command-reference)
4. [Project Structure](#4-project-structure)
5. [Data Pipeline](#5-data-pipeline)
6. [Core Data Model](#6-core-data-model)
7. [Metric Formulas](#7-metric-formulas)
8. [The `rules.json` File](#8-the-rulesjson-file)
9. [Technical Details](#9-technical-details)
10. [References](#10-references)

---

## 1. Installation

### 1.1 Requirements

- **Python**: 3.11 or higher
- **Platforms**: macOS / Linux / Windows (including WSL2) — pure Python, no system libraries required
- **Network**: only the `fetch` step needs access to `api.pinchbench.com`

### 1.2 Install from source

```bash
git clone https://github.com/UnicomAI/pinchbench-upgraded.git
cd pinchbench-upgraded
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -e .                  # add --force-reinstall to forcibly reinstall (including all deps)
```

### 1.3 Uninstall

```bash
pip uninstall pinchbench-upgraded
```

---

## 2. Quick Start

Minimum runnable example — from zero to HTML reports:

```bash
# 1) Fetch data (only step that needs network)
pinchbench-upgraded fetch

# 2) Generate the version inventory report for manual review
pinchbench-upgraded inventory

# 3) Edit current_model_scope_rules.json
#    At minimum set: selected_benchmark_versions, selected_task_ids

# 4) Generate the three-stage outputs (all offline, served from local cache)
pinchbench-upgraded scope
pinchbench-upgraded task-rankings
pinchbench-upgraded category-rankings
```

Outputs land in `pinchbench_data/<version-dir>/analysis/` as HTML / JSON. The HTML files are fully self-contained (inline CSS / JS, base64-embedded logo and fonts) — drop them into GitHub Pages or open with a double-click locally.

---

## 3. Command Reference

### 3.1 Global Options (apply to every subcommand)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--data-dir` | Path | `<package>/pinchbench_data` | Data root directory |
| `--rules-file` | Path | `<package>/current_model_scope_rules.json` | Path to the rules file |

Example:
```bash
pinchbench-upgraded scope --data-dir /tmp/pb --rules-file ./my_rules.json
```

### 3.2 `pinchbench-upgraded fetch`

Fetch the upstream leaderboard and every model's full submissions (list + each detail), writing them to the local cache.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--benchmark-version` | str | current active version | Pin a historical version hash (e.g. `current-newest2.0.0-20260511`) |
| `--force-refresh` | flag | False | Ignore the local cache and re-pull everything |

```bash
pinchbench-upgraded fetch                                      # pull the current active version
pinchbench-upgraded fetch --benchmark-version 2.0.0-20260511   # pin a specific version
pinchbench-upgraded fetch --force-refresh                      # full re-pull
```

### 3.3 `pinchbench-upgraded inventory`

Scan already-fetched data and produce a version inventory report (Markdown + JSON) that helps reviewers fill in `selected_benchmark_versions` and `selected_task_ids`. **No API calls.**

No subcommand-specific options.

```bash
pinchbench-upgraded inventory
```

Output: `analysis/version_inventory/version_inventory_report.{md,json}`

### 3.4 `pinchbench-upgraded scope`

Apply the **four-condition binary validity check** to each submission (see [§6 Core Data Model](#6-core-data-model)) and filter the model set according to `rules.json`. **No API calls** — reads only the local cache from `fetch`.

No subcommand-specific options.

```bash
pinchbench-upgraded scope
```

Output: three JSON files in `analysis/current_model_scope/` (inventory / official_models / summary).

### 3.5 `pinchbench-upgraded task-rankings`

Aggregate the per-task leaderboards for the N canonical tasks (decided by `selected_task_ids`), producing JSON + HTML. **No API calls.**

No subcommand-specific options.

```bash
pinchbench-upgraded task-rankings
```

Output: `analysis/current_task_rankings/current_selected_task_rankings.{json,html}`

### 3.6 `pinchbench-upgraded category-rankings`

Aggregate the per-category leaderboards + overall ranking based on the upstream official categories (JSON + HTML). **No API calls.**

No subcommand-specific options.

```bash
pinchbench-upgraded category-rankings
```

Output: `analysis/current_category_rankings/current_selected_category_rankings.{json,html}`

---

## 4. Project Structure

```
PinchBench-Upgraded/
├── pyproject.toml                       # Package config (name = pinchbench-upgraded, py >= 3.11)
├── LICENSE                              # MIT license
├── README.md / README.en.md             # Documentation (zh / en)
├── SCHEMA_README.md                     # Field reference for the 5 JSON outputs
├── current_model_scope_rules.json       # Rules file (user-maintained)
├── src/pinchbench_upgraded/
│   ├── cli.py                           # CLI entry point (registers the `pinchbench-upgraded` command)
│   ├── config.py                        # Global constants (BASE_URL / retry params, etc.)
│   ├── steps/
│   │   ├── step1_fetch.py
│   │   ├── step1_5_inventory.py
│   │   ├── step2_model_scope.py
│   │   ├── step3_task_rankings.py
│   │   └── step4_category_rankings.py
│   └── html/templates/                  # Jinja2 HTML templates
│       ├── base.html
│       ├── task_rankings.html
│       ├── category_rankings.html
│       └── _filter_bar.html
└── pinchbench_data/                     # Default data directory (created at runtime)
    └── <version-dir>/                   # Isolated per benchmark_version
        ├── leaderboard_current.json
        ├── submissions/                 # API cache
        └── analysis/                    # Step outputs
```

---

## 5. Data Pipeline

Five sequential steps. Step 1 requires network; the other four are fully offline (driven by Step 1's cache):

| Step | Command | Network | Inputs | Outputs |
|------|---------|:-------:|--------|---------|
| 1 | `fetch` | ✅ | API: `api.pinchbench.com` | `leaderboard_current.json` + `submissions/` |
| 1.5 | `inventory` | ❌ | Step 1 output | `version_inventory_report.{md,json}` |
| 2 | `scope` | ❌ | Step 1 output + `rules.json` | `current_model_scope/*.json` |
| 3 | `task-rankings` | ❌ | Step 2 output | `current_selected_task_rankings.{json,html}` |
| 4 | `category-rankings` | ❌ | Step 3 output | `current_selected_category_rankings.{json,html}` |

**Critical handoff**: between Step 1.5 and Step 2 a human edits `rules.json`, filling in the reviewed `selected_benchmark_versions` and `selected_task_ids` (see [§8](#8-the-rulesjson-file)).

---

## 6. Core Data Model

### 6.1 submission: the atomic unit of validation

A *submission* is one complete benchmark run that records the model's score, time, and cost on every task. This tool treats **the entire submission** as the atomic unit when checking validity.

### 6.2 Four-condition binary validity

A submission is marked valid **iff all four conditions hold**:

1. **Version match**: `benchmark_version ∈ selected_benchmark_versions`
2. **Exact task set match**: the set of task_ids in the submission equals the canonical set (no more, no fewer)
3. **Non-zero cost**: `total_cost_usd > 0`
4. **Non-zero task duration**: every task's `execution_time_seconds > 0`

Any failure invalidates the whole submission, classified by **the single highest-priority reason**: `canonical_extra > canonical_missing > task_time_zero > cost_zero`.

> **Granularity note**: The single-reason rule above is at the **submission level** — each failed submission gets exactly one reason. The model-level inventory table (the "filtered-out models" section in the HTML) shows a **count aggregation** of all failed submissions for that model across the 4 reasons — if different submissions of the same model trigger different reasons, the model will check multiple columns in the inventory table.

### 6.3 Core quantities

| Symbol | Meaning |
|--------|---------|
| **K** | Number of submissions that pass §6.2's four conditions (constant across tasks for the same model; K=0 models go to the filtered-out section) |
| **N** | Total canonical task count (decided by `selected_task_ids`) |
| **T** | Number of tasks within a category (T ≤ N; the overall ranking is the T = N special case) |

For detailed field definitions see [SCHEMA_README.md](./SCHEMA_README.md).

---

## 7. Metric Formulas

The HTML tables expose 7 metrics. Aggregation across the three tiers (per-task / per-category / overall) is as follows.

### 7.1 Per-task table

| Metric | Unit | Formula / source |
|--------|------|------------------|
| Runs | times | K |
| Parameters | B | `overrides_model_size` value if listed, otherwise `-` (strict overrides-only) |
| Success rate | % | Σ(score / max_score × 100) / K |
| Cost | USD | Σ(submission cost) / K / N |
| Duration | s | Σ(execution_time_seconds) / K |
| Value | %/USD | success_rate / cost |
| Time Eff. | %/s | success_rate / duration |

Note: cost is "amortized to a single task after completing the full benchmark of N tasks", so **the cost is identical for the same model across tasks** (the upstream submission data has no per-task cost breakdown, so an exact per-task cost cannot be derived).

### 7.2 Per-category / Overall

| Metric | Unit (HTML display) | Formula |
|--------|---------------------|---------|
| Runs | times | K (same as per-task) |
| Success rate | % | avg(success_rate of each task in the category) |
| Cost | USD | per-task cost × T |
| Duration | min | Σ(duration_s of each task in the category) / 60 |
| Value | %/USD | category success rate / category cost |
| Time Eff. | %/min | category success rate / category duration (min) |

Note: the category JSON product stores `avg_duration_min` in minutes (computed at the backend as `sum(avg_duration_s of each task) / 60`); the HTML tables display this value directly, no further `/ 60` at render time. Time efficiency is `%/min` for the same reason. The overall ranking is the T = N special case covering all tasks; for it, category cost degenerates to `Σ(submission cost) / K` (the average total cost of one submission).

---

## 8. The `rules.json` File

`current_model_scope_rules.json` controls validity decisions and presentation attributes. The three-layer contract: `selected_*` + `overrides_*` are human-maintained (code only reads, never writes); `candidates_*` are **rewritten by every `pinchbench-upgraded scope` run**, so you never write them by hand.

### 8.1 Required fields

| Field | Type | Description |
|-------|------|-------------|
| `selected_benchmark_versions` | string[] | The benchmark version hashes that enter the leaderboard (taken from the inventory report) |
| `selected_task_ids` | string[] | The canonical task set (a submission must match this set exactly to be valid) |

### 8.2 Optional fields (human-maintained, code never writes)

| Field | Type | Description |
|-------|------|-------------|
| `overrides_china_prefixes` | `string[]` | Human-confirmed China vendor prefixes (anything not listed is treated as non-China) |
| `overrides_is_open_weight` | `string[]` | Human-confirmed open-weight models (anything not listed is treated as closed, ignoring upstream weights / hf_link) |
| `overrides_model_size` | `{"provider/model": {"model_size_raw": "...", "model_size_b": <num>}}` | Human-supplied parameter counts (anything not listed shows `-` in HTML) |
| `overrides_category_zh` | `{"category_en": "中文"}` | Category English→Chinese translation (anything not listed shows the English original) |
| `overrides_task_zh` | `{"task_id": "任务中文名"}` | Task English→Chinese translation (anything not listed shows the English original) |

All `overrides_*` are edited by humans; the code only reads, never writes. "Ghost" entries from retired versions are allowed and will not be auto-pruned.

### 8.3 Auto-maintained fields (rewritten by every `scope` run)

| Field | Content |
|-------|---------|
| `candidates_china_prefixes` | All vendor prefixes observed in the currently selected versions that are **not** in `overrides_china_prefixes` |
| `candidates_is_open_weight` | All models observed in the currently selected versions that are **not** in `overrides_is_open_weight`, recorded with upstream `weights` / `hf_link` |
| `candidates_model_size` | All models observed in the currently selected versions that are **not** in `overrides_model_size`, recorded with auto-detected suggestions |
| `candidates_category_zh` | All categories observed in the currently selected versions that are **not** in `overrides_category_zh` |
| `candidates_task_zh` | All tasks observed in the currently selected versions that are **not** in `overrides_task_zh` |

Invariant: after every `scope`, `overrides_X ∩ candidates_X = ∅` and `candidates_X = observed_X − overrides_X`. Hence `overrides_X ∪ candidates_X` is a *superset* of the observed set (because `overrides_X` may carry retired ghost entries).

---

## 9. Technical Details

### 9.1 HTTP / retry / cache

- Synchronous `httpx` client
- Exponential-backoff retry via `tenacity` (up to 5 attempts; trigger conditions in `api_client.py:_is_retryable`)
- Tunable inter-request delay (`FETCH_DELAY_MS` in `config.py`, default 500 ms)
- Every API response is persisted to a local cache (one file per submission_id); subsequent steps read offline

### 9.2 HTML rendering

- Jinja2 template inheritance (`base.html` ⊃ `task_rankings.html` / `category_rankings.html`)
- CSS / JS fully inline, logo and Google Fonts (Outfit + JetBrains Mono) embedded as base64 — zero external dependencies
- Language switching via `data-lang` attributes + `body.lang-en` CSS class — no reload
- Filter controls (runs / country / open-source) re-render the tbody live in the browser; no server needed

### 9.3 Static deployment

The generated HTML is self-contained and back-end-free. You can:
- Deploy to GitHub Pages / Cloudflare Pages / Netlify
- Open locally with a double-click (works on `file://`)
- Embed inside a corporate wiki or docs site

---

## 10. References

- **Upstream PinchBench**: [pinchbench.com](https://pinchbench.com/) · [github.com/pinchbench/leaderboard](https://github.com/pinchbench/leaderboard) (MIT-licensed, led by kilo.ai)
- **Task definitions**: [github.com/pinchbench/skill](https://github.com/pinchbench/skill/tree/main)
- **Data API**: [github.com/pinchbench/api](https://github.com/pinchbench/api)
- **Field reference for this tool's outputs**: [SCHEMA_README.md](./SCHEMA_README.md)

## License

MIT — see [LICENSE](./LICENSE).

Thanks to the PinchBench team for publishing the data so the community can do downstream research and presentation on top of real evaluation results.
