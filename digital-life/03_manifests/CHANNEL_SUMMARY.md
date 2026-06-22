# 数字生命 GitHub 上传通道摘要

- 项目目录：`/Users/yu/Documents/Codex/coex项目总库/10-19_四项目工程域/11_P01_数字生命_DL`
- GitHub 目录：`digital-life/`
- 本次策略：正式工程体量大，按红楼梦方法上传接续层与恢复账；小型试运行包此前已在 digital-life-github-starter 中存在。
- 文件数：2876
- 总体量：4527220794 bytes (4.2 GiB)

## 通道统计

| 通道 | 文件数 | 体量 | 说明 |
| --- | ---: | ---: | --- |
| `A_DIRECT_GIT` | 2829 | 28.1 MiB | 可直接进入普通 Git 的小型文本/配置/入口文件。 |
| `B_GIT_LFS_RECOMMENDED` | 6 | 148.0 KiB | 数据库或较大文件，建议 Git LFS 或本地备份。 |
| `B_GIT_LFS_REQUIRED` | 19 | 4.1 GiB | 超过普通 GitHub 单文件限制，必须 Git LFS 或本地/Release 备份。 |
| `C_INDEX_FIRST_THEN_SELECTIVE_UPLOAD` | 7 | 14.3 MiB | 输出层/生成层，先上传索引，再按需要择要上传。 |
| `C_RELEASE_OR_LOCAL_BACKUP` | 9 | 67.2 MiB | 压缩包、恢复包或备份包，登记清单后走 Release/本地备份。 |
| `D_LOCAL_RUNTIME_ONLY` | 6 | 42.0 KiB | 本地运行状态、缓存、嵌套 Git 或锁定现场，不进普通仓库。 |

## 已生成清单

- `03_manifests/upload_channel_manifest.csv`：全量文件通道清单。
- `03_manifests/large_files_manifest.csv`：大文件、数据库、压缩包、非直接 Git 文件清单，含 sha256（需要时）。
- `03_manifests/top_level_size_report.csv`：顶层目录体量统计。
- `03_manifests/entry_candidates.csv`：入口、规则、启动、README 候选。
- `03_manifests/entry_sample_index.csv`：已复制到包内的入口样本索引。

## 当前结论

工程体量或文件形态不适合一次性进入普通 Git；采用红楼梦方法：GitHub 保留接续入口、规则、索引和恢复账，本地保留完整运行现场。
