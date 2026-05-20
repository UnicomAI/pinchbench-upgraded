# PinchBench-Upgraded 版本盘点报告

- 生成时间: 2026-05-20T02:56:46.258239+00:00
- 数据目录: `C:\Users\LiuYutong\Desktop\work\13大模型能力边界量化\龙虾攻关\PinchBench_Upgraded\pinchbench_data\current-newest2.0.0-20260520`
- 数据基础: **全量 submissions**（每模型在该版本下跑过的所有 submission 任务并集）
- 已扫描 detail 文件: 476（跳过 0）
- (model, provider, version) 唯一键: 43
- benchmark_version 数: 1

## 1. 版本概览

| 版本 ID | 官方模型 | 全部模型 | 官方 submissions | 全部 submissions | 独有任务总数 | 任务集分布（任务并集大小:模型数） |
|---------|----------|----------|------------------|------------------|--------------|-----------------------------------|
| `2.0.0` | 43 | 43 | 476 | 476 | 147 | 147:40 / 123:3 |

> 「任务集分布」基于每个模型在该版本下跑过的**全部 submission 任务并集**——比基于 best 单条更稳健。

## 2. 任务覆盖明细（按版本，覆盖模型数 = 在该版本下至少跑过一次该任务的官方模型数）

### 版本 `2.0.0`（官方模型 43 个，独有任务 147 个，官方 submissions 476 条）

| 任务 ID | 覆盖模型数 | 占比 |
|---------|------------|------|
| `task_access_log_anomaly` | 43 | 100% |
| `task_blog` | 43 | 100% |
| `task_browser_automation` | 43 | 100% |
| `task_byok_best_practices` | 43 | 100% |
| `task_calendar` | 43 | 100% |
| `task_cicd_pipeline_debug` | 43 | 100% |
| `task_clawdhub` | 43 | 100% |
| `task_codebase_navigation` | 43 | 100% |
| `task_commit_message_writer` | 43 | 100% |
| `task_competitive_research` | 43 | 100% |
| `task_contract_analysis` | 43 | 100% |
| `task_cron_organizer` | 43 | 100% |
| `task_csv_cities_density` | 43 | 100% |
| `task_csv_cities_filter` | 43 | 100% |
| `task_csv_cities_growth` | 43 | 100% |
| `task_csv_cities_ranking` | 43 | 100% |
| `task_csv_finance_report` | 43 | 100% |
| `task_csv_gdp_per_capita` | 43 | 100% |
| `task_csv_gdp_ranking` | 43 | 100% |
| `task_csv_gdp_regions` | 43 | 100% |
| `task_csv_iris_classify` | 43 | 100% |
| `task_csv_iris_outliers` | 43 | 100% |
| `task_csv_iris_summary` | 43 | 100% |
| `task_csv_life_exp_change` | 43 | 100% |
| `task_csv_life_exp_outliers` | 43 | 100% |
| `task_csv_life_exp_ranking` | 43 | 100% |
| `task_csv_pension_liability` | 43 | 100% |
| `task_csv_pension_ranking` | 43 | 100% |
| `task_csv_pension_risk` | 43 | 100% |
| `task_csv_stations_by_elevation` | 43 | 100% |
| `task_csv_stations_coverage` | 43 | 100% |
| `task_csv_stations_filter` | 43 | 100% |
| `task_csv_stock_best_worst` | 43 | 100% |
| `task_csv_stock_trend` | 43 | 100% |
| `task_csv_stock_volatility` | 43 | 100% |
| `task_csv_temp_anomalies` | 43 | 100% |
| `task_csv_temp_decades` | 43 | 100% |
| `task_csv_temp_trend` | 43 | 100% |
| `task_cve_security_triage` | 43 | 100% |
| `task_daily_summary` | 43 | 100% |
| `task_deep_research` | 43 | 100% |
| `task_dockerfile_optimization` | 43 | 100% |
| `task_earnings_analysis` | 43 | 100% |
| `task_eli5_pdf_summary` | 43 | 100% |
| `task_email` | 43 | 100% |
| `task_email_reply_drafting` | 43 | 100% |
| `task_email_search` | 43 | 100% |
| `task_email_triage` | 43 | 100% |
| `task_eu_regulation_research` | 43 | 100% |
| `task_events` | 43 | 100% |
| `task_executive_lookup` | 43 | 100% |
| `task_files` | 43 | 100% |
| `task_financial_ratio_calculation` | 43 | 100% |
| `task_gh_issue_triage` | 43 | 100% |
| `task_git_rescue_recovery` | 43 | 100% |
| `task_gws_cross_service` | 43 | 100% |
| `task_gws_email_triage` | 43 | 100% |
| `task_gws_task_management` | 43 | 100% |
| `task_humanizer` | 43 | 100% |
| `task_image_gen` | 43 | 100% |
| `task_image_identification` | 43 | 100% |
| `task_it_procurement` | 43 | 100% |
| `task_iterative_code_refine` | 43 | 100% |
| `task_k8s_debugging` | 43 | 100% |
| `task_log_apache_client_issues` | 43 | 100% |
| `task_log_apache_critical` | 43 | 100% |
| `task_log_apache_error_summary` | 43 | 100% |
| `task_log_apache_timeline` | 43 | 100% |
| `task_log_apache_top_errors` | 43 | 100% |
| `task_log_syslog_boot` | 43 | 100% |
| `task_market_research` | 43 | 100% |
| `task_meeting_advisory_acronyms` | 43 | 100% |
| `task_meeting_advisory_attendees` | 43 | 100% |
| `task_meeting_advisory_stakeholders` | 43 | 100% |
| `task_meeting_advisory_technical` | 43 | 100% |
| `task_meeting_advisory_timeline` | 43 | 100% |
| `task_meeting_blog_post` | 43 | 100% |
| `task_meeting_council_budget` | 43 | 100% |
| `task_meeting_council_contact_info` | 43 | 100% |
| `task_meeting_council_neighborhood` | 43 | 100% |
| `task_meeting_council_public_comment` | 43 | 100% |
| `task_meeting_council_upcoming` | 43 | 100% |
| `task_meeting_council_votes` | 43 | 100% |
| `task_meeting_executive_summary` | 43 | 100% |
| `task_meeting_follow_up_email` | 43 | 100% |
| `task_meeting_gov_controversy` | 43 | 100% |
| `task_meeting_gov_data_sources` | 43 | 100% |
| `task_meeting_gov_next_steps` | 43 | 100% |
| `task_meeting_gov_qa_extract` | 43 | 100% |
| `task_meeting_gov_recommendations` | 43 | 100% |
| `task_meeting_gov_speaker_summary` | 43 | 100% |
| `task_meeting_searchable_index` | 43 | 100% |
| `task_meeting_sentiment_analysis` | 43 | 100% |
| `task_meeting_tech_action_items` | 43 | 100% |
| `task_meeting_tech_competitors` | 43 | 100% |
| `task_meeting_tech_decisions` | 43 | 100% |
| `task_meeting_tech_messaging` | 43 | 100% |
| `task_meeting_tech_product_features` | 43 | 100% |
| `task_meeting_tldr` | 43 | 100% |
| `task_memory` | 43 | 100% |
| `task_multi_file_refactoring` | 43 | 100% |
| `task_openclaw_comprehension` | 43 | 100% |
| `task_oss_alternative_research` | 43 | 100% |
| `task_pdf_to_calendar` | 43 | 100% |
| `task_playwright_e2e` | 43 | 100% |
| `task_polymarket_briefing` | 43 | 100% |
| `task_pricing_research` | 43 | 100% |
| `task_readme_generation` | 43 | 100% |
| `task_sanity` | 43 | 100% |
| `task_second_brain` | 43 | 100% |
| `task_selector_fix` | 43 | 100% |
| `task_session_chain_analysis` | 43 | 100% |
| `task_shell_command_generator` | 43 | 100% |
| `task_skill_search` | 43 | 100% |
| `task_spreadsheet_summary` | 43 | 100% |
| `task_stock` | 43 | 100% |
| `task_subway_navigation` | 43 | 100% |
| `task_summary` | 43 | 100% |
| `task_test_generation` | 43 | 100% |
| `task_todo_list_cleanup` | 43 | 100% |
| `task_video_transcript_extraction` | 43 | 100% |
| `task_weather` | 43 | 100% |
| `task_workflow` | 43 | 100% |
| `task_log_hdfs_block_ops` | 40 | 93% |
| `task_log_hdfs_connections` | 40 | 93% |
| `task_log_hdfs_failures` | 40 | 93% |
| `task_log_hdfs_slow_ops` | 40 | 93% |
| `task_log_hdfs_storage` | 40 | 93% |
| `task_log_mapreduce_failures` | 40 | 93% |
| `task_log_mapreduce_jobs` | 40 | 93% |
| `task_log_mapreduce_resources` | 40 | 93% |
| `task_log_mapreduce_slow_tasks` | 40 | 93% |
| `task_log_mapreduce_timeline` | 40 | 93% |
| `task_log_nginx_errors` | 40 | 93% |
| `task_log_nginx_slow_requests` | 40 | 93% |
| `task_log_nginx_status_codes` | 40 | 93% |
| `task_log_nginx_traffic` | 40 | 93% |
| `task_log_nginx_user_agents` | 40 | 93% |
| `task_log_ssh_brute_force` | 40 | 93% |
| `task_log_ssh_failed_logins` | 40 | 93% |
| `task_log_ssh_successful` | 40 | 93% |
| `task_log_ssh_unusual_times` | 40 | 93% |
| `task_log_ssh_user_activity` | 40 | 93% |
| `task_log_syslog_anomalies` | 40 | 93% |
| `task_log_syslog_auth_failures` | 40 | 93% |
| `task_log_syslog_cron` | 40 | 93% |
| `task_log_syslog_services` | 40 | 93% |

## 3. 操作指引

将以下两个字段填入 `current_model_scope_rules.json`（项目根目录），再运行 `pinchbench-upgraded scope`：

```json
{
  "selected_benchmark_versions": ["2.0.0"],
  "selected_task_ids": ["task_access_log_anomaly", "task_blog", "task_browser_automation", ...]
}
```

### 选择策略

- **完整集**：取选定版本所有任务（数据量最大，覆盖度低的模型会被剔除）
- **兼容集**：取选定版本内所有官方模型都跑过的任务（数据量小，模型保留率高）
- **覆盖率门槛**：选取覆盖模型数 ≥ 选定版本官方模型数 50% 的任务（折中方案）

Step 2 对每条 submission 做四条件二元有效性判定：①版本匹配 ②submission 的 task_id 集合精确等于 canonical 集合 ③`total_cost_usd > 0` ④每个 task 的 `execution_time_seconds > 0`；任意失败则该 submission 整体失效，按 `canonical_extra > canonical_missing > task_time_zero > cost_zero` 单一归类。模型的 valid submission 数 K=0 时进入「筛除模型」区——选 canonical 时应避开覆盖过低的任务，否则少数模型会因 canonical_missing 被淘汰。
