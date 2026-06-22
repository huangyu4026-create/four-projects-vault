# 四项目工程 GitHub 同步标准

生成时间：2026-06-22

## 总目标

GitHub 作为版本账本、接续入口、规则索引、恢复清单和后续施工台；本地保留完整运行现场、大型数据库、恢复包和临时产物。

## 决策原则

1. 不因隐私主动排除文件；用户已确认没有隐私排除要求。
2. 不把普通 GitHub 仓库当作大文件仓库。
3. 能直接进 Git 的内容优先上传。
4. 超过普通 GitHub 限制或不适合普通 Git 管理的内容，登记路径、大小、修改时间和校验值。
5. 每个工程必须保留本地完整备份责任说明。
6. 每次同步都能回答：GitHub 有什么、本地还必须保存什么、后续如何恢复。

## 上传通道

- `A_DIRECT_GIT`：小型入口、规则、索引、脚本、说明、清单，直接进入 GitHub。
- `B_GIT_LFS_REQUIRED`：超过普通 GitHub 单文件限制的大文件，后续走 Git LFS。
- `B_GIT_LFS_RECOMMENDED`：接近或超过警告阈值的大文件，建议走 Git LFS。
- `C_RELEASE_OR_LOCAL_BACKUP`：压缩包、恢复包、快照包，建议走 Release 附件或本地完整备份。
- `C_INDEX_FIRST_THEN_SELECTIVE_UPLOAD`：大量生成输出，先建索引，再按需要选择上传。
- `D_LOCAL_RUNTIME_ONLY`：缓存、临时日志、运行态文件，默认只做本地保留或索引。

## 每个工程的标准目录

```text
<project>/
  README.md
  00_entry/
  01_rules/
  02_key_scripts_or_tools/
  03_manifests/
  04_backup_plan/
```

## 本地必须另备

1. 完整工程根目录。
2. SQLite / 数据库 / 关系库 / 搜索库。
3. `.bak`、`.zip`、`.tar.gz`、稳定节点包。
4. 关键 outputs、运行记录、恢复包。
5. 当前可运行环境和本地服务目录。
