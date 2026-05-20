# PinchBench-Upgraded

> 🇬🇧 [English](README.en.md)

跨平台 Python 工具，对上游 [PinchBench](https://pinchbench.com/) 公开数据做二次处理，产出交互式中英双语 HTML 排行榜。

**逐任务排行榜** (./pinchbench_data/current-newest2.0.0-20260520/analysis/current_task_rankings/current_selected_task_rankings.html)

**大类聚合排行榜**(./pinchbench_data/current-newest2.0.0-20260520/analysis/current_task_rankings/current_selected_category_rankings.html)



**核心特性**：以**单次提交（submission）**为最小粒度做二元有效性判定 → 严格版本管理 → 任务级 / 大类级 / 总排行榜三层聚合 → 7 指标自包含 HTML（成功率 / 成本 / 耗时 / 性价比 / 时效比 / 参数量 / 运行次数）→ 国别 + 开源属性筛选。

数据来源：[PinchBench](https://pinchbench.com/)（[MIT 协议开源](https://github.com/pinchbench/leaderboard)，由 kilo.ai 主导）。本工具不修改任何模型的原始提交数据，仅做有效性校验与聚合呈现，感谢 PinchBench 团队开放数据。

---

## 目录

1. [安装](#1-安装)
2. [快速开始](#2-快速开始)
3. [命令参考](#3-命令参考)
4. [项目结构](#4-项目结构)
5. [数据流水线](#5-数据流水线)
6. [核心数据模型](#6-核心数据模型)
7. [指标公式](#7-指标公式)
8. [rules.json 规则文件](#8-rulesjson-规则文件)
9. [技术细节](#9-技术细节)
10. [参考](#10-参考)

---

## 1. 安装

### 1.1 系统要求

- **Python**：3.11 或更高
- **平台**：macOS / Linux / Windows（含 WSL2）—— 纯 Python 实现，无系统库依赖
- **网络**：仅 `fetch` 阶段需访问 `api.pinchbench.com`

### 1.2 从源码安装

```bash
git clone https://github.com/UnicomAI/pinchbench-upgraded.git
cd pinchbench-upgraded
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -e .                  # 加 --force-reinstall 可强制覆盖重装（含所有依赖）
```

### 1.3 卸载

```bash
pip uninstall pinchbench-upgraded
```

---

## 2. 快速开始

最小可运行示例 —— 从零到 HTML 报告：

```bash
# 1) 抓数据（唯一联网步骤）
pinchbench-upgraded fetch

# 2) 生成版本盘点报告，供人工审核
pinchbench-upgraded inventory

# 3) 编辑 current_model_scope_rules.json
#    至少填入：selected_benchmark_versions、selected_task_ids

# 4) 生成三阶段产物（全部离线，命中本地缓存）
pinchbench-upgraded scope
pinchbench-upgraded task-rankings
pinchbench-upgraded category-rankings
```

产物位置：`pinchbench_data/<version-dir>/analysis/` 下的 HTML / JSON。HTML 文件完全自包含（CSS / JS 内联、logo base64 嵌入），可直接 GitHub Pages 部署或本地双击打开。

---

## 3. 命令参考

### 3.1 全局参数（所有子命令通用）

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--data-dir` | Path | `<package>/pinchbench_data` | 数据根目录 |
| `--rules-file` | Path | `<package>/current_model_scope_rules.json` | 规则文件路径 |

示例：
```bash
pinchbench-upgraded scope --data-dir /tmp/pb --rules-file ./my_rules.json
```

### 3.2 `pinchbench-upgraded fetch`

抓取上游 leaderboard 与每个模型的全部 submissions（list + 每条 detail），写入本地缓存。

| 专属参数 | 类型 | 默认值 | 说明 |
|---------|------|--------|------|
| `--benchmark-version` | str | 当前活跃版 | 指定历史版本 hash（如 `current-newest2.0.0-20260511`） |
| `--force-refresh` | flag | False | 忽略本地缓存，强制重新拉取所有数据 |

```bash
pinchbench-upgraded fetch                                      # 拉当前活跃版
pinchbench-upgraded fetch --benchmark-version 2.0.0-20260511   # 指定版本
pinchbench-upgraded fetch --force-refresh                      # 全量重拉
```

### 3.3 `pinchbench-upgraded inventory`

扫描已抓数据，生成版本盘点报告（Markdown + JSON），帮助人工审核 `selected_benchmark_versions` 与 `selected_task_ids` 的取值。**不发起 API 调用**。

无专属参数。

```bash
pinchbench-upgraded inventory
```

输出：`analysis/version_inventory/version_inventory_report.{md,json}`

### 3.4 `pinchbench-upgraded scope`

对每条 submission 做**四条件二元有效性判定**（参见 [§6 核心数据模型](#6-核心数据模型)），按 `rules.json` 筛选模型范围。**不发起 API 调用**，仅读取 fetch 阶段的本地缓存。

无专属参数。

```bash
pinchbench-upgraded scope
```

输出：`analysis/current_model_scope/` 下三份 JSON（inventory / official_models / summary）。

### 3.5 `pinchbench-upgraded task-rankings`

按任务粒度聚合 N 个 canonical 任务（由 `selected_task_ids` 决定）的排行榜（JSON + HTML）。**不发起 API 调用**。

无专属参数。

```bash
pinchbench-upgraded task-rankings
```

输出：`analysis/current_task_rankings/current_selected_task_rankings.{json,html}`

### 3.6 `pinchbench-upgraded category-rankings`

按上游官方分类聚合大类排行榜 + 总排行榜（JSON + HTML）。**不发起 API 调用**。

无专属参数。

```bash
pinchbench-upgraded category-rankings
```

输出：`analysis/current_category_rankings/current_selected_category_rankings.{json,html}`

---

## 4. 项目结构

```
PinchBench-Upgraded/
├── pyproject.toml                       # 包配置（name = pinchbench-upgraded, py >= 3.11）
├── LICENSE                              # MIT 协议
├── README.md                            # 本文档
├── README.en.md                         # 英文版
├── SCHEMA_README.md                     # 5 个 JSON 产物的字段说明
├── current_model_scope_rules.json       # 规则文件（由用户维护）
├── src/pinchbench_upgraded/
│   ├── cli.py                           # CLI 入口（pinchbench-upgraded 命令注册）
│   ├── config.py                        # 全局常量（BASE_URL / 重试参数等）
│   ├── steps/
│   │   ├── step1_fetch.py
│   │   ├── step1_5_inventory.py
│   │   ├── step2_model_scope.py
│   │   ├── step3_task_rankings.py
│   │   └── step4_category_rankings.py
│   └── html/templates/                  # Jinja2 HTML 模板
│       ├── base.html
│       ├── task_rankings.html
│       ├── category_rankings.html
│       └── _filter_bar.html
└── pinchbench_data/                     # 默认数据目录（运行时生成）
    └── <version-dir>/                   # 按 benchmark_version 隔离
        ├── leaderboard_current.json
        ├── submissions/                 # API 缓存
        └── analysis/                    # 各 step 产物
```

---

## 5. 数据流水线

5 步顺序执行，第 1 步联网，其余 4 步均本地处理（基于 Step 1 的缓存）：

| Step | 命令 | 联网 | 输入 | 输出 |
|------|------|:----:|------|------|
| 1 | `fetch` | ✅ | API: `api.pinchbench.com` | `leaderboard_current.json` + `submissions/` |
| 1.5 | `inventory` | ❌ | Step 1 输出 | `version_inventory_report.{md,json}` |
| 2 | `scope` | ❌ | Step 1 输出 + `rules.json` | `current_model_scope/*.json` |
| 3 | `task-rankings` | ❌ | Step 2 输出 | `current_selected_task_rankings.{json,html}` |
| 4 | `category-rankings` | ❌ | Step 3 输出 | `current_selected_category_rankings.{json,html}` |

**关键节点**：Step 1.5 与 Step 2 之间需要人工编辑 `rules.json`，填入审核确认的 `selected_benchmark_versions` 与 `selected_task_ids`（见 [§8](#8-rulesjson-规则文件)）。

---

## 6. 核心数据模型

### 6.1 submission：最小校验单位

「单次提交（submission）」是一次完整的 benchmark 跑测记录，包含该模型在所有任务上的得分、用时、成本。本工具以**整份 submission** 为单位做有效性判定。

### 6.2 四条件二元有效性

一份 submission 当且仅当满足**全部 4 个条件**时才被标记为 valid：

1. **版本匹配**：`benchmark_version ∈ selected_benchmark_versions`
2. **任务集精确匹配**：submission 中 task_id 集合 = canonical 任务集（不多不少）
3. **成本非零**：`total_cost_usd > 0`
4. **任务耗时非零**：所有 task 的 `execution_time_seconds > 0`

任意条件不满足 → 该 submission 整体失效，按**单一最高优先级原因**归类：`canonical_extra > canonical_missing > task_time_zero > cost_zero`。

> **粒度说明**：上述单一归类是 **submission 粒度**——每条失效 submission 只记一个原因。模型级 inventory 表（HTML "筛除模型" 区）展示的是该模型所有失效 submission 在 4 个原因上的**计数聚合**——若同一模型的不同 submission 触发了不同原因，则该模型在 inventory 表中会同时命中多列。

### 6.3 核心量

| 符号 | 含义 |
|------|------|
| **K** | 该模型满足 §6.2 四条件的 valid submission 数（跨任务对同模型恒定；K=0 模型进入「筛除」section） |
| **N** | canonical 任务总数（由 `selected_task_ids` 决定） |
| **T** | 大类内的任务数（T ≤ N；总排行榜是 T = N 的特例） |

详细字段定义见 [SCHEMA_README.md](./SCHEMA_README.md)。

---

## 7. 指标公式

HTML 排行表展示 7 个指标。任务级 / 大类级 / overall 三层聚合规则如下：

### 7.1 任务级（单任务排行表）

| 指标 | 单位 | 公式 / 来源 |
|------|------|------|
| 运行次数 | 次 | K |
| 参数量 | B | `overrides_model_size` 命中时取该值，否则显示 `-`（严格 overrides-only） |
| 成功率 | % | Σ(score / max_score × 100) / K |
| 成本 | USD | Σ(submission cost) / K / N |
| 耗时 | s | Σ(execution_time_seconds) / K |
| 性价比 | %/USD | 成功率 / 成本 |
| 时效比 | %/s | 成功率 / 耗时 |

注：成本按"完成全套 benchmark（N 任务）后摊算到单任务"计算，因此**同模型跨任务的 cost 相同**（上游 submission 维度无 per-task cost 分布，无法严格分摊到单任务）。

### 7.2 大类级 / 总排行榜

| 指标 | 单位（HTML 显示） | 公式 |
|------|------|------|
| 运行次数 | 次 | K（与任务级相同） |
| 成功率 | % | avg(大类内各任务 success_rate) |
| 成本 | USD | 任务级成本 × T |
| 耗时 | min | Σ(大类内各任务 duration_s) / 60 |
| 性价比 | %/USD | 大类成功率 / 大类成本 |
| 时效比 | %/min | 大类成功率 / 大类耗时（min） |

注：category JSON 产物里 `avg_duration_min` 字段单位为分钟（由后端 `sum(各 task 的 avg_duration_s) / 60` 计算落库），HTML 表格直接展示该值，无需前端再除 60；时效比同理直接为 `%/min`。总排行榜 = T = N 的特例，覆盖全部任务，此时大类成本退化为 `Σ(submission cost) / K`（一份 submission 的平均总成本）。

---

## 8. rules.json 规则文件

`current_model_scope_rules.json` 控制有效性判定与展示属性。三层契约：`selected_*` + `overrides_*` 由人工维护、代码只读不写；`candidates_*` 由 `pinchbench-upgraded scope` **每次运行自动重写**，无需手工填写。

### 8.1 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `selected_benchmark_versions` | string[] | 进入榜单的 benchmark 版本 hash 列表（来自 inventory 报告） |
| `selected_task_ids` | string[] | canonical 任务集（提交需精确等于此集合才算有效）|

### 8.2 选填字段（人工维护，代码只读不写）

| 字段 | 类型 | 说明 |
|------|------|------|
| `overrides_china_prefixes` | `string[]` | 人工确认的中国厂商前缀（未列入即视为非中国）|
| `overrides_is_open_weight` | `string[]` | 人工确认的开源模型清单（未列入即视为闭源，无视上游 weights / hf_link）|
| `overrides_model_size` | `{"provider/model": {"model_size_raw": "...", "model_size_b": 数字}}` | 人工填的参数量（未列入即视为未知，HTML 显示 `-`）|
| `overrides_category_zh` | `{"category_en": "中文"}` | 大类英→中翻译表（未列入即显示英文原名）|
| `overrides_task_zh` | `{"task_id": "任务中文名"}` | 任务英→中翻译表（未列入即显示英文原名）|

所有 `overrides_*` 都由人工编辑维护，代码**只读不写**。允许保留已下线的"幽灵条目"，下次 scope 不会自动删除。

### 8.3 自动维护字段（代码每次 scope 重写）

| 字段 | 内容 |
|------|------|
| `candidates_china_prefixes` | 当前选中版本观测到所有**非** `overrides_china_prefixes` 的厂商前缀 |
| `candidates_is_open_weight` | 当前选中版本观测到所有**非** `overrides_is_open_weight` 的模型 + 上游 weights/hf_link 实录 |
| `candidates_model_size` | 当前选中版本观测到所有**非** `overrides_model_size` 的模型 + 自动检测建议值 |
| `candidates_category_zh` | 当前选中版本观测到所有**非** `overrides_category_zh` 的大类 |
| `candidates_task_zh` | 当前选中版本观测到所有**非** `overrides_task_zh` 的任务 |

不变量：每次 scope 写回后 `overrides_X ∩ candidates_X = ∅`，且 `candidates_X = observed_X − overrides_X`。所以 `overrides_X ∪ candidates_X` 是当前选中版本观测全集的超集（因为 overrides 可能含已下线条目）。

---

## 9. 技术细节

### 9.1 HTTP / 重试 / 缓存

- 基于 `httpx` 同步客户端
- `tenacity` 指数退避重试（最多 5 次，触发条件见 `api_client.py:_is_retryable`）
- 请求间隔可调（`config.py` 中 `FETCH_DELAY_MS`，默认 500 ms）
- 所有 API 响应落本地缓存（按 submission_id 分文件存储），后续 step 离线读取

### 9.2 HTML 渲染

- Jinja2 模板继承（`base.html` ⊃ `task_rankings.html` / `category_rankings.html`）
- CSS / JS 完全内联，logo 与 Google Fonts（Outfit + JetBrains Mono）以 base64 data URI 嵌入 —— 零外部资源依赖
- 中英文切换通过 `data-lang` 属性 + `body.lang-en` CSS class，无需重载
- 筛选条件（运行次数 / 国别 / 开源）通过前端 JS 即时重渲染 tbody，无需服务端

### 9.3 静态部署

生成的 HTML 自包含且不依赖任何后端，可直接：
- 部署到 GitHub Pages / Cloudflare Pages / Netlify
- 本地双击在浏览器中打开（支持 `file://` 协议）
- 嵌入企业 Wiki 或文档站

---

## 10. 参考

- **上游 PinchBench**：[pinchbench.com](https://pinchbench.com/) · [github.com/pinchbench/leaderboard](https://github.com/pinchbench/leaderboard)（MIT 协议，由 kilo.ai 主导）
- **任务详情**：[github.com/pinchbench/skill](https://github.com/pinchbench/skill/tree/main)
- **数据 API**：[github.com/pinchbench/api](https://github.com/pinchbench/api)
- **本工具数据字段说明**：[SCHEMA_README.md](./SCHEMA_README.md)

## License

MIT — 见 [LICENSE](./LICENSE)。

致谢 PinchBench 团队公开数据，使社区可以基于真实测评结果进行二次研究与展示。
