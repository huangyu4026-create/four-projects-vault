# 工作生活计划 GitHub 接续卡

## 远端结论

- 本地根目录：`/Users/yu/Documents/Codex/coex项目总库/20-29_工具域/21_T01_工作生活计划工具_WCC`
- GitHub 目录：`work-life-plan/`
- 文件数：11345
- 总体量：705.4 MiB
- 策略：文件数多且含运行时/嵌套 Git，按红楼梦方法先上传接续层与恢复账，再分批筛选源码和规则。

## 通道统计

| 通道 | 文件数 | 体量 |
| --- | ---: | ---: |
| `A_DIRECT_GIT` | 613 | 7.7 MiB |
| `C_RELEASE_OR_LOCAL_BACKUP` | 2 | 51.1 KiB |
| `D_LOCAL_RUNTIME_ONLY` | 10730 | 697.6 MiB |

## 顶层体量

| 顶层目录 | 文件数 | 体量 |
| --- | ---: | ---: |
| `40_加工区` | 5359 | 655.3 MiB |
| `50_输出区` | 5462 | 47.3 MiB |
| `00_域门` | 417 | 2.5 MiB |
| `10_输入收件箱` | 105 | 189.9 KiB |
| `20_规则与流程` | 2 | 22.1 KiB |

## 本地备份责任

- GitHub 保存入口、清单、规则索引和恢复账。
- 本地继续保存完整根目录，尤其是大型 SQLite、压缩恢复包、输出归档和运行时现场。
- `D_LOCAL_RUNTIME_ONLY` 不逐个列入远端恢复账；需要时整体备份本地根目录即可。
- 有 sha256 的文件可用 `shasum -a 256 "文件路径"` 校验。

## 大文件/恢复账 CSV

```csv
relative_path,size_bytes,human_size,extension,channel,sha256
50_输出区/来源路径保留/2026-06-15/new-chat/outputs/轻量工程回显迁移备份_20260616/work_plan_recall_server_20260614版.py.bak,26007,25.4 KiB,.bak,C_RELEASE_OR_LOCAL_BACKUP,71400e13a3b62bc5f9286c584d9b1876e6c6b28875a9075ae905384521b4c4cb
50_输出区/来源路径保留/2026-06-15/new-chat/outputs/轻量工程回显迁移备份_20260616/work_plan_recall_server_20260615版.py.bak,26320,25.7 KiB,.bak,C_RELEASE_OR_LOCAL_BACKUP,2ec16520250db7d5c180db07a8d1a897a7e4e498b72e0cf8823284b4df19098a
```
