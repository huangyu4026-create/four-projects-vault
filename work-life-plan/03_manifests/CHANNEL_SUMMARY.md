# 工作生活计划 GitHub 上传通道摘要

- 项目目录：`/Users/yu/Documents/Codex/coex项目总库/20-29_工具域/21_T01_工作生活计划工具_WCC`
- GitHub 目录：`work-life-plan/`
- 本次策略：文件数多且含运行时/嵌套 Git，按红楼梦方法先上传接续层与恢复账，再分批筛选源码和规则。
- 文件数：11345
- 总体量：739616631 bytes (705.4 MiB)

## 通道统计

| 通道 | 文件数 | 体量 | 说明 |
| --- | ---: | ---: | --- |
| `A_DIRECT_GIT` | 613 | 7.7 MiB | 可直接进入普通 Git 的小型文本/配置/入口文件。 |
| `C_RELEASE_OR_LOCAL_BACKUP` | 2 | 51.1 KiB | 压缩包、恢复包或备份包，登记清单后走 Release/本地备份。 |
| `D_LOCAL_RUNTIME_ONLY` | 10730 | 697.6 MiB | 本地运行状态、缓存、嵌套 Git 或锁定现场，不进普通仓库。 |

## 已生成清单

- `03_manifests/upload_channel_manifest.csv`：全量文件通道清单。
- `03_manifests/large_files_manifest.csv`：大文件、数据库、压缩包、非直接 Git 文件清单，含 sha256（需要时）。
- `03_manifests/top_level_size_report.csv`：顶层目录体量统计。
- `03_manifests/entry_candidates.csv`：入口、规则、启动、README 候选。
- `03_manifests/entry_sample_index.csv`：已复制到包内的入口样本索引。

## 当前结论

工程体量或文件形态不适合一次性进入普通 Git；采用红楼梦方法：GitHub 保留接续入口、规则、索引和恢复账，本地保留完整运行现场。
