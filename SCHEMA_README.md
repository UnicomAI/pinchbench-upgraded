# JSON 产物字段说明

PinchBench-Upgraded 流水线总共产出 6 份 JSON 文件，本文档逐字段说明含义与公式。完整数据流与设计哲学见 [`README.md`](./README.md)。

## 文件清单

```
pinchbench_data/<version-dir>/analysis/
├── version_inventory/
│   ├── version_inventory_report.json        # 版本盘点（inventory 命令）
│   └── version_inventory_report.md          # 同上，人审用 Markdown 版
├── current_model_scope/
│   ├── current_model_inventory.json         # 全部官方模型逐行完整记录
│   ├── current_all_official_models.json     # = inventory 中 official=True 的子集
│   └── current_model_scope_summary.json     # 顶层统计 + 自描述字段
├── current_task_rankings/
│   └── current_selected_task_rankings.json  # 任务级排行（含 N 个 task 表）
└── current_category_rankings/
    └── current_selected_category_rankings.json   # 大类排行 + 总排行榜
```

**字段对齐方法论**：每张表后给的字段清单基于代码实际写出（`step1_5_inventory.py` / `step2_model_scope.py` / `step3_task_rankings.py` / `step4_category_rankings.py`）。下游消费方只读这些字段。

---

## 1. `version_inventory_report.json`

由 `pinchbench-upgraded inventory` 产出，扫描 `submissions/current/*.json` 全量 detail 缓存，按 `(model, provider, benchmark_version)` 聚合统计。用于人审决策 `rules.json` 里的 `selected_benchmark_versions` 与 `selected_task_ids`。

### 顶层

| 字段 | 类型 | 说明 |
|------|------|------|
| `generated_at` | string | ISO 8601 UTC 生成时间 |
| `data_dir` | string | 数据根目录绝对路径 |
| `submissions_dir` | string | 扫描的 detail 目录路径 |
| `detail_files_scanned` | int | 成功读入的 detail 文件数 |
| `detail_files_skipped` | int | 因 IO 错误跳过的 detail 文件数 |
| `unique_keys` | int | `(model, provider, version)` 唯一键数量 |
| `version_count` | int | 出现过的 benchmark_version 数量 |
| `data_basis` | string | 固定 `"full_submissions"`（基于全量 submission 任务并集统计，非 best 单条） |
| `versions` | list[dict] | 每条对应一个 benchmark_version 的统计 |

### `versions[i]` 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | benchmark_version hash 或 semver（如 `"2.0.0"`） |
| `official_model_count` | int | 该版本下有 `official=true` submission 的模型数 |
| `total_model_count` | int | 该版本下出现的全部模型数（含非官方） |
| `official_submission_count` | int | 官方 submission 总数 |
| `total_submission_count` | int | 全部 submission 总数 |
| `all_task_id_count` | int | 该版本下出现过的不同 task_id 数 |
| `task_distribution` | dict[int → int] | `{该模型在该版本下跑过的任务并集大小: 处于此并集大小的模型数}`，键按并集大小降序 |
| `task_coverage` | dict[str → int] | `{task_id: 跑过该任务的官方模型数}`，按覆盖数降序、再按 task_id 升序 |
| `all_task_ids` | list[str] | 该版本下出现过的 task_id 排序列表 |

Markdown 版（`.md`）由同一份 JSON 渲染，章节为：①版本概览 ②任务覆盖明细 ③操作指引。

---

## 2. `current_model_inventory.json`

由 `pinchbench-upgraded scope` 产出。**每条 = 一个模型**（按 leaderboard 排名升序排列），当前数据下含 42 行。

### 模型基础身份

| 字段 | 类型 | 说明 |
|------|------|------|
| `model` | string | 模型完整 ID，如 `anthropic/claude-opus-4.7` |
| `model_prefix` | string | 厂商前缀，如 `anthropic/` |
| `provider` | string | 提供方，如 `openrouter` |
| `leaderboard_rank` | int | 上游 leaderboard 中的排名 |
| `best_score_percentage` | float | 上游 best submission 的总分百分比 |
| `leaderboard_submission_count` | int\|null | 上游 leaderboard 显示的提交次数（参考） |
| `submissions_total` | int\|null | 该模型跨版本全部 submission 数（参考） |
| `returned_submission_count` | int\|null | 本次 list API 实际返回的 submission 数 |
| `latest_submission` | string\|null | 最新一份 submission 的时间戳 |
| `best_submission_id` | string | best submission 的 ID（用来读出此模型的属性元数据） |
| `benchmark_version` | string | best submission 所在的 benchmark 版本 |
| `official` | bool | 上游 submission 是否标 `official=true` |
| `weights` | string\|null | 上游 `weights` 字段原值：`"Open"` / `"Closed"` / `"Unknown"` / null |
| `hf_link` | string\|null | Hugging Face 链接（如有） |

### 元数据（开源 / 参数量 / 国别——严格 overrides-only 分类）

| 字段 | 类型 | 说明 |
|------|------|------|
| `model_size_raw` | string\|null | 参数量原文（如 `"70b"` / `"35b-a3b"`）。**仅当模型在 `overrides_model_size` 中**才有值，否则 null（HTML 显示 `-`） |
| `model_size_b` | float\|null | 参数量（B 为单位）。同上 |
| `is_china_model` | bool | `model_prefix in overrides_china_prefixes` → true，否则 false |
| `china_reason` | string\|null | `"override"`（命中）或 `null`（未命中） |
| `is_open_weight_model` | bool | `model in overrides_is_open_weight` → true，否则 false（**无视上游 weights / hf_link**） |
| `open_weight_reason` | string\|null | `"override"` 或 `null` |

### 核心：submission 级二元有效性

| 字段 | 类型 | 说明 |
|------|------|------|
| `valid_submission_count` | int | **K**：选定 benchmark 版本下满足 4 条件的 submission 数（= 排行榜"运行次数"） |
| `valid_submission_ids` | list[str] | K 份 valid submission 的 ID 列表（顺序保留；step3 据此读 detail 累加指标） |
| `invalid_reasons` | dict[str, int] | 失效 submission 按原因码计数，4 个固定 key：`canonical_extra` / `canonical_missing` / `task_time_zero` / `cost_zero` |
| `sample_invalid_submissions` | list[dict] | 每原因码取 ≤2 份样本供 HTML 诊断（见下） |

`sample_invalid_submissions[i]` 字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `submission_id` | string | 失效 submission ID |
| `reason` | string | 命中的原因码 |
| `missing_tasks` | list[str] | 仅 `canonical_missing` 时出现，最多列前 5 个缺失 task_id |
| `missing_tasks_truncated` | bool | `len(missing_tasks) > 5` 时为 true，提示有截断 |
| `extra_tasks` | list[str] | 仅 `canonical_extra` 时出现，最多列前 5 个多出 task_id |
| `extra_tasks_truncated` | bool | 同上 |

**有效性 4 条件**（同时满足才算 valid，否则按下方优先级归类失效）：

1. 版本前置过滤：`submission.benchmark_version ∈ rules.selected_benchmark_versions` —— 不满足直接前置过滤掉，**不计入** `invalid_reasons`
2. `set(submission.tasks[*].task_id) == rules.selected_task_ids`（集合相等）
3. `submission.usage_summary.total_cost_usd > 0`
4. **全部** `submission.tasks[i].execution_time_seconds > 0`

**失效原因码归类优先级**：`canonical_extra` > `canonical_missing` > `task_time_zero` > `cost_zero`。

---

## 3. `current_all_official_models.json`

定义为 `inventory` 中 `official=True` 的子集。**当前数据下与 inventory 字节一致**（上游 leaderboard API 默认只返回 official 模型，所以 `unofficial_models == 0`）。

保留独立文件是为了语义稳定——若未来 leaderboard 开始混入 unofficial，两份文件会自然产生差异。

---

## 4. `current_model_scope_summary.json`

scope 步骤的顶层统计 + 自描述字段。下游可用作仪表盘。

### 顶层元数据

| 字段 | 说明 |
|------|------|
| `generated_at` | 与上游 leaderboard 一致的生成时间戳 |
| `selected_benchmark_versions` | 来自 rules 的版本数组，如 `["2.0.0"]` |
| `canonical_task_ids` | rules 指定的 canonical 任务 ID 排序列表 |
| `selected_task_ids_count` | rules 指定的 canonical 任务数（应 == `len(canonical_task_ids)`） |
| `canonical_task_count` | **N** = canonical 任务总数 |

### 模型数量分布

| 字段 | 说明 |
|------|------|
| `current_total_models` | 上游 leaderboard 返回的全部模型数 |
| `official_models` | 标 `official=true` 的模型数 |
| `unofficial_models` | 非官方模型数（当前 = 0） |
| `ranking_model_count` | 进入排行榜的模型数（= `valid_submission_count > 0` 的官方模型数） |
| `filtered_out_count` | 被筛除的模型数（= `valid_submission_count == 0` 的官方模型数） |

### Submission 级聚合

| 字段 | 说明 |
|------|------|
| `total_valid_submissions` | 跨全部官方模型的 valid submission 总数 |
| `total_invalid_submissions` | 跨全部官方模型的 invalid submission 总数 |
| `aggregate_invalid_reasons` | dict<原因码, 总数>，跨全部官方模型按 4 原因码汇总 |

### 筛除模型清单

| 字段 | 说明 |
|------|------|
| `filtered_out_models` | list[dict]，每条含 `model` / `provider` / `invalid_reasons` / `primary_reason`（主要原因码） |

### 规则维护统计

| 字段 | 说明 |
|------|------|
| `rules_file` | 规则文件绝对路径 |
| `rules_file_existed_before_run` | 本次运行前文件是否已存在（首次跑会生成空种子） |
| `overrides_china_prefix_count` | rules 中已维护的中国前缀数 |
| `candidates_china_prefix_count` | 自动重生的非中国前缀待审数 |
| `overrides_model_size_count` | rules 中已维护的参数量条目数 |
| `candidates_model_size_count` | 自动重生的待审参数量模型数 |

### 自描述字段

`official_definition` / `canonical_source` / `submission_validity_definition` / `open_weight_definition` / `china_definition` / `model_size_definition` / `depends_on`

下游代码通常不消费这些，纯供人读。

---

## 5. `current_selected_task_rankings.json`

由 `pinchbench-upgraded task-rankings` 产出。结构含**顶层透传** + 三个主要数组（`models` / `tasks` / `categories`）。

### 顶层（17 字段）

| 字段 | 说明 |
|------|------|
| `generated_at` | 本次 task-rankings 步骤生成时间（UTC） |
| `source_generated_at` | 透传自 scope_summary（= 上游 leaderboard 生成时间） |
| `current_total_models` / `official_models` | 透传自 scope_summary |
| `selected_benchmark_versions` | 透传 |
| `total_valid_submissions` / `total_invalid_submissions` | 透传 |
| `ranking_model_count` / `filtered_out_count` | 透传 |
| `filtered_out_models` | 透传（每条 4 字段：`model` / `provider` / `invalid_reasons` / `sample_invalid_submissions`） |
| `canonical_task_count` | **N** |
| `task_count` | 任务表数（理论上 == N，例外见下方注） |
| `output_sorting` | 字符串自描述排序规则 |
| `models` | 排名模型清单（见下） |
| `tasks` | N 张任务表（见下） |
| `categories` | 大类与任务索引（见下） |
| `metrics_definition` | dict<指标名, 中文定义>，自描述 |

### `models[i]` 字段（10 个，每模型一行）

| 字段 | 说明 |
|------|------|
| `provider`, `model` | 模型标识 |
| `model_size_raw`, `model_size_b` | 参数量（来源 overrides） |
| `is_open_weight_model`, `is_china_model`, `is_open_weight_and_china` | 三个 bool（最后一个 = 前两个的 AND，方便前端筛选） |
| `run_count` | K |
| `total_submission_count` | K + sum(invalid_reasons) = 选定版本下的总提交数 |
| `sum_total_cost_usd` | K 份 valid submission 的 cost 之和 |

### `tasks[i]` 字段（每条对应一个 canonical task）

| 字段 | 说明 |
|------|------|
| `task_id` | canonical task 标识 |
| `task_name` | 上游 frontmatter.name（英文）|
| `task_name_zh` | `overrides_task_zh` 命中时的中文译名，否则同 `task_name` |
| `category` | 归一化小写英文大类（如 `"coding"`） |
| `category_zh` | `overrides_category_zh` 命中时的中文译名，否则同 `category` |
| `grading_type` | 评分类型（透传自上游） |
| `row_count` | 该任务下排行的模型行数 |
| `rows` | 排行数组（见下） |

### `tasks[i].rows[j]` 字段（11 个，每行 = 1 个模型在该 task 上的指标）

| 字段 | 单位 | 公式 / 来源 |
|------|------|------|
| `rank` | — | 按 `output_sorting` 规则计算 |
| `model`, `provider` | — | 模型标识 |
| `model_size_raw`, `model_size_b` | — | 透传自 inventory |
| `run_count` | 次 | K（模型级单值，跨任务相同） |
| `average_success_rate_pct` | % | sum(score / max_score × 100) / K |
| `cost_per_run_usd` | USD | sum(submission `total_cost_usd`) / K / N |
| `avg_duration_s` | 秒 | sum(`execution_time_seconds`) / K |
| `value_score` | %/USD | `average_success_rate_pct / cost_per_run_usd`（>0 时计算） |
| `time_efficiency` | %/秒 | `average_success_rate_pct / avg_duration_s`（>0 时计算，2 位小数） |

### `categories[i]` 字段（4 个，HTML 侧边栏「大类与任务」索引）

| 字段 | 说明 |
|------|------|
| `category_name_en` | 归一化小写英文大类名 |
| `category_name_zh` | 中文译名（命中 `overrides_category_zh` 否则同 en） |
| `task_count` | 该大类下任务数 T |
| `tasks` | list[{`task_id`, `task_name_en`, `task_name_zh`}] |

### `output_sorting` 字段

字面值（const）："按 `average_success_rate_pct` 从高到低；同分按 `value_score`、`avg_duration_s`、`model` 稳定排序"。

### `metrics_definition` 字段

dict 自描述 `run_count` / `success_rate` / `cost_per_run_usd` / `avg_duration_s` / `value_score` 的含义，纯供人读。

> **注**：`all_data_json` 是 step3 内部为 HTML 准备的嵌入数据（写到 HTML `<script id="ranking-data">` 里），**不在 JSON 顶层产物中**——由 `step3_task_rankings.py:411` 显式过滤掉。下游 JSON 消费方不会看到此字段。

---

## 6. `current_selected_category_rankings.json`

由 `pinchbench-upgraded category-rankings` 产出。结构与 task_rankings 类似，但 `categories` 数组里每条**带有 `rows`**（大类内每个模型一行聚合指标），并额外有一个特殊的 `overall` 总排行榜。

### 顶层（16 字段）

字段同 task_rankings 顶层，差异：
- **无** `output_sorting` / `task_count` / `tasks` 字段
- **新增** `category_count`（= 大类数，自动按 `task.category` 分组得出，当前 11）
- **新增** `overall`：总排行榜（结构与 `categories[i]` 一致，task_ids 含全部 N）
- `metrics_definition` 字段集不同（含 `category_source` / `exclusion` 等）

### `categories[i]` 字段（7 个）

| 字段 | 说明 |
|------|------|
| `category_name_en`, `category_name_zh` | 大类英文 / 中文名 |
| `task_count` | T（该大类内 task 数） |
| `task_ids` | 该大类下 task_id 排序列表 |
| `tasks` | list[{`task_id`, `task_name_en`, `task_name_zh`}] |
| `row_count` | 该大类下排行的模型数 |
| `rows` | 大类聚合后的排行数组（每行同 task_rankings.rows 结构，11 字段） |

### `overall` 字段（特殊大类）

结构与 `categories[i]` 完全相同，外加 `is_overall: true`，其 `task_ids` 覆盖全部 N 个 canonical 任务。

### 大类聚合公式

每个 row 与 task row 的 11 字段一致；指标值按下方公式从该模型在该大类内 T 个 task 上的指标聚合：

| 指标 | 公式 | 备注 |
|------|------|------|
| `run_count` | K | 模型级单值 |
| `average_success_rate_pct` | `avg(各 task 的 success_rate)` | T 个任务取均值 |
| `cost_per_run_usd` | `任务级 cost × T` | 等价于 `sum(submission cost) × T / K / N` |
| `avg_duration_min` | `sum(各 task 的 avg_duration_s) / 60` | 单位分钟（与 cost 求和语义对称；完成 T 个任务的总耗时） |
| `value_score` | `大类 success_rate / 大类 cost` | 2 位小数 |
| `time_efficiency` | `大类 success_rate / 大类 avg_duration_min` | 单位 `%/min`（每分钟可获得的成功率），2 位小数 |

**总排行榜（`overall`，T = N）的退化关系**：`cost_per_run_usd == sum(submission cost) / K == sum_total_cost_usd / K`（一份 submission 的平均总成本）。

> **注**：与 task_rankings 一样，`all_data_json` 仅嵌入 HTML，不在此 JSON 顶层。

---

## 7. 数学不变性（回归校验用）

### 对每个**官方模型**

```
valid_submission_count   == 任意 task row 的 run_count
                        == 任意 category row 的 run_count
                        == overall row 的 run_count
sum(invalid_reasons.values()) + valid_submission_count
                        == 选定版本下的 submission 数
                        == models[i].total_submission_count
valid_submission_count == 0  ⟺  模型在 filtered_out_models  ⟺  不在排行榜
```

### 对 `scope_summary` 顶层

```
official_models = ranking_model_count + filtered_out_count
total_valid_submissions + total_invalid_submissions
    == 跨全部官方模型在选定版本下的 submission 总数
sum(aggregate_invalid_reasons.values()) == total_invalid_submissions
unofficial_models == 0  ⇒  inventory == all_official_models (byte-identical)
```

### 对任务级 vs 大类级（同一模型）

```
# 「一份 valid submission 跑完全部 N 个任务一次」的平均总成本
overall.cost_per_run_usd
  == 任意 task row.cost_per_run_usd × N          # 任务级 cost 是「单 task 摊到 N 个」的均值，乘 N 还原
  == sum(submission.total_cost_usd) / K
  == sum_total_cost_usd / K                      # 按 sum_total_cost_usd 的定义

# 「一份 valid submission 跑完全部 N 个任务一次」的平均总耗时（单位分钟）
overall.avg_duration_min
  == sum(各 task row.avg_duration_s) / 60        # task 单位秒，sum 后除 60 转分钟
  == sum_over_K_and_tasks(execution_time) / K / 60  # 等价展开：跨 K 跨 task 全和 / K / 60
```

---

## 8. 数据流位置

```
fetch              → submissions/current_lists/         (list 缓存)
                     submissions/current/                (detail 缓存)
                     leaderboard_current.json
inventory          → analysis/version_inventory/         (盘点报告，供人审决策)
scope              → analysis/current_model_scope/       (3 个 JSON：inventory / all_official / summary)
                     current_model_scope_rules.json      (rules 文件：overrides 不动，candidates_* 自动重生)
task-rankings      → analysis/current_task_rankings/     (JSON + HTML)
category-rankings  → analysis/current_category_rankings/ (JSON + HTML)
```

完整设计哲学与代码结构见 [`README.md`](./README.md)。
