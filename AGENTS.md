# Four Projects Vault Agent Rules

## 工程 Git 正式落点硬规则

- 当用户说“进入工程”“进入某某工程”“按固定 Git 入口工作”，或开始维护某个长期工程时，第一动作不是直接改散目录，而是先确认正式 Git 仓库根目录。
- 必须优先核对：`git rev-parse --show-toplevel`、`git remote -v`、`git status --short`。
- 如果当前目录不是 Git 仓库，必须先查找该工程是否已有正式 Git 镜像或仓库落点；找到后在仓库内施工。找不到时才报告“当前仅为本地游离目录，未入 Git”，并询问是否建立或连接仓库。
- 不得同时维护两个正式目录。历史目录、施工旧址、同步副本只能作为来源、查证或迁移参照；正式修改必须落在已确认的 Git 仓库工作区。
- 形成清楚工程节点后，必须检查 `git status`，说明改动文件和验证结果；提交或推送前要获得用户确认。推送只表示推到用户自己的远端仓库，不等于公开发布。


## 红楼梦工程入口硬规则

- 用户说“进入红楼梦工程”“进入红楼梦人工智能咨询工程”“进入红楼梦人工咨询工程”“进入坐标查询”“红楼梦工程”等表达时，默认都是同一条当前正式线：红楼梦人工智能咨询工程的坐标查询线。
- 第一动作必须确认正式 Git 仓库根目录：`/Users/yu/Documents/Codex/2026-06-22/new-chat-4/work/four-projects-vault-sync-20260622-final`。
- 正式远端是：`origin https://github.com/huangyu4026-create/four-projects-vault.git`。正式工程目录是仓库内的 `红楼梦人工智能咨询工程/`。
- 进入后必须先核对：

```bash
git -C /Users/yu/Documents/Codex/2026-06-22/new-chat-4/work/four-projects-vault-sync-20260622-final rev-parse --show-toplevel
git -C /Users/yu/Documents/Codex/2026-06-22/new-chat-4/work/four-projects-vault-sync-20260622-final remote -v
git -C /Users/yu/Documents/Codex/2026-06-22/new-chat-4/work/four-projects-vault-sync-20260622-final status --short
```

- 维护入口、策略、卡值、固定点、脚本、模板时，正式写入目标只能是 `/Users/yu/Documents/Codex/2026-06-22/new-chat-4/work/four-projects-vault-sync-20260622-final/红楼梦人工智能咨询工程/`。`/Users/yu/Documents/Codex/2026-06-03/notion-3-crv` 只作历史来源、查证来源或迁移参照，除非用户明确要求维护旧址。
- 当前坐标线入口优先读仓库内 `红楼梦人工智能咨询工程/00_entry_and_route/000C_进入坐标查询_新窗口强制入口.md`，再读 `红楼梦人工智能咨询工程/00_entry_and_route/000E_B_坐标工程查询逻辑策略经验模板组_新窗口学习入口.md`；固定点副本用于校验一致性。
- 不得把旧“语义/聚拢搜索”和当前“坐标查询”重新做成两个并列入口、两个头、两个门。旧闭环/聚拢资料可以作为历史参照；当前正式入口以坐标查询线为准。
- 坐标查询类任务必须保留子问题拆分、查询词策略、查询词、查询逻辑策略、取词查表策略、现场修正活账和入池凭证；用户讨论“子问题”“策略”“取词”“继续修正/完善”时，应回到已记录的相应状态继续，而不是重新编一个过程。


## 仓库内工作规则

- 本仓库是用户自己的 `four-projects-vault` 工作区。提交和推送只代表写入用户自己的仓库历史，不代表公开发布。
- 修改 `红楼梦人工智能咨询工程/` 时，优先保持入口文件、固定点文件和 `02_key_scripts/` 的规则一致；改完必须运行可行的语法检查或最小流程检查，并报告验证结果。
- 如果发现旧文件仍提到双头、旧语义聚拢入口或游离目录正式落点，先标明是历史资料还是当前规则；不要让旧规则覆盖当前坐标查询线。
