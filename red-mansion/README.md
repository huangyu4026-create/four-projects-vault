# 红楼梦工程 GitHub 接续包

生成时间：2026-06-22 11:08:46

本包来自本地真实工程根目录：

```text
/Users/yu/Documents/Codex/2026-06-03/notion-3-crv
```

本地工程总量：

```text
文件数：19438
总大小：4724152488 bytes
```

## 本包用途

本包不是把 4.5G 本地运行现场硬塞进普通 Git，而是把后续接手最需要的入口、规则、关键脚本、上传通道清单和备份责任放进仓库。

## 使用顺序

1. 先读 `00_entry_and_route/000_进入红楼梦工程_新窗口强制入口.md`。
2. 再读 `131 / 127 / 128 / 117 / 119 / 120` 这些工程路线和聚拢总图规则。
3. 需要运行或修复时，从 `02_key_scripts/` 里的关键脚本进入。
4. 需要追完整本地资产时，读 `03_manifests/CHANNEL_SUMMARY.md`、`03_manifests/large_files_manifest.csv` 和本地输出包中的 `upload_channel_manifest.csv`。

## 2026-06-22 坐标升级

今天新增 `05_coordinate_mapping_20260622/`：这是红楼梦新版坐标总库的 GitHub 接续层。它记录正式坐标总库从 2706 个退役来源段升级到 3754 个新版原子段，并保留双头入口、坐标取材到材料池验收、A/B 复核设计跑、关键脚本、SQLite schema、表行数和本地大库 sha256 清单。

2026-06-24 状态更新：`05_coordinate_mapping_20260622/` 暂时停用为主入口，只作为历史固定点和证据留档保留。坐标/咨询类问题后续主用顶层 `红楼梦人工智能咨询工程/`；普通聚拢题仍按旧入口链读取。

## 上传通道原则

- `A_DIRECT_GIT`：适合直接进入普通 GitHub 仓库。
- `B_GIT_LFS_REQUIRED` / `B_GIT_LFS_RECOMMENDED`：适合 Git LFS，普通 Git 可能失败或警告。
- `C_RELEASE_OR_LOCAL_BACKUP`：适合 Release 附件或本地完整备份。
- `D_LOCAL_RUNTIME_ONLY`：运行缓存、日志、临时状态，默认不作为仓库功能面。
