# 哲思之旅 GitHub 接续卡

## 远端结论

- 本地根目录：`/Users/yu/Documents/Codex/coex项目总库/10-19_四项目工程域/14_P04_哲思之旅_ZS`
- GitHub 目录：`philosophy-journey/`
- 文件数：357
- 总体量：22.7 MiB
- 策略：体量中小，适合直接进 Git；当前先上传接续层、清单和备份账，后续命令行 Git 授权后可整包推送。

## 通道统计

| 通道 | 文件数 | 体量 |
| --- | ---: | ---: |
| `A_DIRECT_GIT` | 352 | 17.7 MiB |
| `C_INDEX_FIRST_THEN_SELECTIVE_UPLOAD` | 2 | 4.9 MiB |
| `D_LOCAL_RUNTIME_ONLY` | 3 | 24.0 KiB |

## 顶层体量

| 顶层目录 | 文件数 | 体量 |
| --- | ---: | ---: |
| `60_同步记录` | 224 | 13.9 MiB |
| `10_输入收件箱` | 24 | 6.4 MiB |
| `20_规则与流程` | 69 | 1.7 MiB |
| `50_输出区` | 12 | 715.9 KiB |
| `00_域门` | 21 | 47.1 KiB |
| `40_加工区` | 6 | 30.1 KiB |
| `30_正文底库或工具数据` | 1 | 159 B |

## 本地备份责任

- GitHub 保存入口、清单、规则索引和恢复账。
- 本地继续保存完整根目录，尤其是大型 SQLite、压缩恢复包、输出归档和运行时现场。
- `D_LOCAL_RUNTIME_ONLY` 不逐个列入远端恢复账；需要时整体备份本地根目录即可。
- 有 sha256 的文件可用 `shasum -a 256 "文件路径"` 校验。

## 大文件/恢复账 CSV

```csv
relative_path,size_bytes,human_size,extension,channel,sha256
10_输入收件箱/来源路径保留/2026-06-03/notion-3-crv/哲思之旅/哲思之旅工程/17_Notion同步库/哲思之旅项目收件箱/待处理/GPTLINK-001_原始抓取/GPTLINK-001_capture_2026-06-13T15-42-24-138Z.json,2169451,2.1 MiB,.json,C_INDEX_FIRST_THEN_SELECTIVE_UPLOAD,
60_同步记录/来源路径保留/2026-06-03/notion-3-crv/哲思之旅/哲学学习工程分类_files/哲学学习工程分类.html,2982696,2.8 MiB,.html,C_INDEX_FIRST_THEN_SELECTIVE_UPLOAD,
```
