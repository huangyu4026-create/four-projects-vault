# 本身即美 GitHub 接续卡

## 远端结论

- 本地根目录：`/Users/yu/Documents/Codex/coex项目总库/10-19_四项目工程域/12_P02_本身即美_BJM`
- GitHub 目录：`body-is-beauty/`
- 文件数：339
- 总体量：10.5 MiB
- 策略：体量中小，适合直接进 Git；当前先上传接续层、清单和备份账，后续命令行 Git 授权后可整包推送。

## 通道统计

| 通道 | 文件数 | 体量 |
| --- | ---: | ---: |
| `A_DIRECT_GIT` | 334 | 5.4 MiB |
| `C_INDEX_FIRST_THEN_SELECTIVE_UPLOAD` | 2 | 5.0 MiB |
| `C_RELEASE_OR_LOCAL_BACKUP` | 1 | 36.3 KiB |
| `D_LOCAL_RUNTIME_ONLY` | 2 | 12.0 KiB |

## 顶层体量

| 顶层目录 | 文件数 | 体量 |
| --- | ---: | ---: |
| `60_同步记录` | 160 | 8.7 MiB |
| `50_输出区` | 102 | 1.3 MiB |
| `00_域门` | 25 | 214.4 KiB |
| `20_规则与流程` | 25 | 158.3 KiB |
| `10_输入收件箱` | 22 | 89.6 KiB |
| `40_加工区` | 5 | 84.1 KiB |

## 本地备份责任

- GitHub 保存入口、清单、规则索引和恢复账。
- 本地继续保存完整根目录，尤其是大型 SQLite、压缩恢复包、输出归档和运行时现场。
- `D_LOCAL_RUNTIME_ONLY` 不逐个列入远端恢复账；需要时整体备份本地根目录即可。
- 有 sha256 的文件可用 `shasum -a 256 "文件路径"` 校验。

## 大文件/恢复账 CSV

```csv
relative_path,size_bytes,human_size,extension,channel,sha256
00_域门/来源路径保留/2026-06-15/new-chat/outputs/轻量工程回显迁移备份_20260616/本身即美_总输入口.html.bak,37181,36.3 KiB,.bak,C_RELEASE_OR_LOCAL_BACKUP,fc29d5d7bb89ff9e1798ac95a0d71d95ccd9daa00967d5b0eb077400be28cbb2
60_同步记录/来源路径保留/2026-06-03/notion-3-crv/本身即美/本身即美｜建设平台（总根）/无标题 3399-7bbb/nse-360395718674772923-838.jpg,2874446,2.7 MiB,.jpg,C_INDEX_FIRST_THEN_SELECTIVE_UPLOAD,
60_同步记录/来源路径保留/2026-06-03/notion-3-crv/本身即美/本身即美｜建设平台（总根）/无标题 3399-7bbb/nse-5401848676548735946-839.jpg,2405915,2.3 MiB,.jpg,C_INDEX_FIRST_THEN_SELECTIVE_UPLOAD,
```
