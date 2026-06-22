# 数字生命 本地备份责任

- 本地根目录：`/Users/yu/Documents/Codex/coex项目总库/10-19_四项目工程域/11_P01_数字生命_DL`
- GitHub 目录：`digital-life/`

## GitHub 已承担

- 版本化保存入口说明、规则摘要、工程清单和恢复账。
- 保存大文件 sha256，使以后能校验本地备份是否仍是同一份。
- 给后续 Codex 工作一个稳定的接续地址。

## 仍需本地或外部备份

- `B_GIT_LFS_REQUIRED` / `B_GIT_LFS_RECOMMENDED`：数据库、大文件、超 GitHub 普通限制文件。
- `C_RELEASE_OR_LOCAL_BACKUP`：压缩包、恢复包、阶段归档。
- `D_LOCAL_RUNTIME_ONLY`：运行时缓存、锁文件、嵌套 Git、临时进程现场。
- 如需跨机器恢复，优先备份整个本地根目录；至少备份 `large_files_manifest.csv` 中列出的文件。

## 校验方法

对清单中有 sha256 的文件，在本地运行：

```bash
shasum -a 256 "文件路径"
```

输出值应与 `03_manifests/large_files_manifest.csv` 的 `sha256` 列一致。
