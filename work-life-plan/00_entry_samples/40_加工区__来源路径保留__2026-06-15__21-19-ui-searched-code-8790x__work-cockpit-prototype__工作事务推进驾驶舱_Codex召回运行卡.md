# 工作事务推进驾驶舱｜Codex召回运行卡

## 核心判断

桌面入口不是 AI 大脑。

它只负责：

1. 收下原始长文。
2. 写入正式收件箱。
3. 写入 Codex 召回队列。
4. 显示编号和处理状态。
5. 按编号召回结果。

真正的分类、拆任务、时间判断、负责人判断、完成标准判断，由 Codex 读取队列后完成。

## 本地文件

- 桌面入口：`desktop-entry.html`
- 主驾驶舱：`index.html`
- 本地召回服务：`work_plan_recall_server.py`
- Codex 定时接手器：`work_plan_recall_autoworker.py`
- 桌面快捷入口：`工作事务推进驾驶舱桌面入口.command`
- 正式收件箱：`工作事务推进驾驶舱收件箱/`
- 召回队列：`工作事务推进驾驶舱_Codex召回队列.md`
- 召回结果目录：`工作事务推进驾驶舱_Codex召回结果/`
- 结果索引：`工作事务推进驾驶舱_Codex召回结果索引.json`

## 日常流程

```text
桌面入口提交长文
  ↓
本地服务生成 WP 编号
  ↓
写入正式收件箱 + 召回队列 + 结果索引（排队中）
  ↓
服务端自动触发定时接手器
  ↓
接手器标记“处理中”，交给 Codex 阅读原文并输出任务计划
  ↓
Codex 用 complete 命令回写结果，成功标记“已答复”
  ↓
桌面入口按编号召回结果；失败则显示“运行失败”原因
```

## 启动服务

```bash
python3 outputs/work-cockpit-prototype/work_plan_recall_server.py serve --port 8798
```

打开：

```text
http://127.0.0.1:8798/desktop-entry.html
```

## 启动全链路

日常使用优先启动全链路：

```bash
outputs/work-cockpit-prototype/一键启动工作事务推进驾驶舱全链路.command
```

它会同时启动：

1. 本地召回服务：负责页面提交、结果查询、HTML 回显。
2. 服务端自动拉起 Codex 定时接手器：每 10 秒检查一次召回队列，发现待处理 WP 编号后交给 Codex 处理。

定时接手器参考数字生命 `131_codex_recall_autoworker.py`：页面不做智能判断，只写队列；接手器定时取件；Codex 处理；处理器回写 HTML。

## 桌面图标（推荐）

```bash
cp "/Users/yu/Documents/Codex/2026-06-14/skill-2/outputs/work-cockpit-prototype/工作事务推进驾驶舱桌面入口.command" ~/Desktop/
```

把 `工作事务推进驾驶舱桌面入口.command` 拖到桌面后直接双击即可：  
1. 尝试连接 `http://127.0.0.1:8798/desktop-entry.html`  
2. 未检测到服务时自动启动 `一键启动工作事务推进驾驶舱全链路.command`  
3. 服务可用后自动打开桌面入口页

如果你希望自动把图标放到桌面，可以双击运行：

```bash
outputs/work-cockpit-prototype/安装工作事务推进驾驶舱桌面图标.command
```

重要：日常流程不需要手动 `complete`。`complete` 只是 Codex 接手器内部回写结果时调用的程序接口。

## Codex 处理队列

查看最新项：

```bash
python3 outputs/work-cockpit-prototype/work_plan_recall_server.py show latest
```

手动处理一次队列：

```bash
python3 outputs/work-cockpit-prototype/work_plan_recall_autoworker.py
```

持续定时处理：

```bash
python3 outputs/work-cockpit-prototype/work_plan_recall_autoworker.py --daemon --interval 10
```

手动回写只用于调试，不作为日常流程：

```bash
python3 outputs/work-cockpit-prototype/work_plan_recall_server.py complete --id latest --summary "工作计划拆解" --result-file /path/to/result.md
```

## Codex 输出要求

Codex 处理长文时，输出必须包含：

1. 任务表：任务名称、日期、负责人、类别、工作类型、优先级、完成标准。
2. 时间计划：按日期排列，空日期可保留。
3. 分类视图：小红书、清风别墅、生活、学习、外出、其他。
4. 待补条件：缺负责人、缺时间、缺完成标准、需确认事项。
5. 回显摘要：让桌面入口第一屏能看懂结果。

## 结果清单与 Manifest

每一次召回完成后，必须同时生成两类结果：

1. 单条 HTML 结果页：放在 `工作事务推进驾驶舱_Codex召回结果/`。
2. 全局结果索引：写入 `工作事务推进驾驶舱_Codex召回结果索引.json`。

结果索引必须至少包含：

```json
{
  "id": "WP-20260614-204311",
  "status": "已处理",
  "summary": "工作计划拆解：口播、护照、转让书",
  "question": "用户原始输入",
  "created": "2026-06-14 20:43:11",
  "updated": "2026-06-14 20:48:25",
  "result_file": "本地 HTML 文件绝对路径",
  "result_html": "/results/WP-....html",
  "result_json": "/results/WP-....json",
  "result_summary": "第一屏摘要"
}
```

桌面入口只按 `entry_id / WP 编号` 读取这个索引，不再从页面内部猜任务。

## 桌面召回窗口行为

提交后，桌面入口必须立刻显示：

```text
已正式收件
编号：WP-...
状态：排队中
原始输入摘要
```

接手器取件后，桌面入口必须显示：

```text
状态：处理中
Codex 正在拆任务、排日期、生成计划表
```

完成后，桌面入口必须显示：

```text
状态：已答复
结果摘要
打开 HTML 结果页
```

如果后台接手器失败，桌面入口必须显示：

```text
状态：运行失败
失败原因
```

如果轮询超时，不能显示失败完成，只能显示：

```text
后台可能仍在处理，可稍后刷新或查看召回队列。
```

## API 形状

本工程当前采用最小本地 API：

```text
POST /api/submit
GET  /api/result?id=WP-...
GET  /api/results
GET  /results/<result.html>
```

`POST /api/submit` 只负责快速收件，不等待 Codex 完成。

## 后台行为

提交时必须做：

1. 生成 `WP-YYYYMMDD-HHMMSS` 编号。
2. 写入正式收件箱 Markdown。
3. 更新 `工作事务推进驾驶舱_Codex召回队列.md`。
4. 在结果索引中插入 `排队中`。
5. 自动触发一次后台接手器。
6. 立即返回编号给页面。

定时接手器必须做：

1. 定时读取召回队列。
2. 找到第一个未处理 WP 编号。
3. 建立运行锁。
4. 将该编号状态改为 `处理中`。
5. 给 Codex 生成专用 prompt。
6. Codex 读取原文并生成结构化结果。
7. 调用 `work_plan_recall_server.py complete` 回写。
8. 标记为 `已答复`。
9. 如果 Codex 超时、退出或没有回写，标记为 `运行失败` 并写入原因。
10. 释放运行锁。

## 运行锁与恢复

定时接手器必须使用锁，避免两个处理器重复处理同一条：

```text
runtime/work_plan_recall_worker/worker.lock
```

处理规则：

- 如果锁存在且未过期，跳过本轮。
- 如果锁过期，允许下一轮重新处理。
- 每次处理结束都必须释放锁。

后续要补的恢复能力：

- 服务启动时扫描 `待Codex处理` 项。
- 如果有结果文件但索引未更新，自动修复索引。
- 如果队列有未处理但结果索引缺失，补写索引。

## 独立监听器

`work_plan_recall_autoworker.py` 是独立监听器，必须能脱离 HTML 页面运行：

```bash
python3 outputs/work-cockpit-prototype/work_plan_recall_autoworker.py
python3 outputs/work-cockpit-prototype/work_plan_recall_autoworker.py --daemon --interval 10
```

它的职责是：

- 扫描正式召回队列。
- 读取未处理项。
- 调用 Codex。
- 生成结果。
- 回写索引。

页面关闭时，监听器仍然可以处理队列。

## 答案质量闸门

结果页第一屏必须先回答用户真正要的工作计划，不要先解释机制。

工作计划类结果必须优先展示：

1. 哪几件事。
2. 哪一天做。
3. 谁负责。
4. 属于哪个分类。
5. 完成标准是什么。
6. 哪些条件还不清楚。

再往下才放：

- 分类视图。
- 待补条件。
- 解释与注意事项。
- 机制回执。

## 常见失败与修复

### 页面自己硬判长文

修复：删除或降级前端规则，页面只提交原文和显示结果。

### 已收件但没有处理

检查：

- `工作事务推进驾驶舱_Codex召回队列.md` 是否有未处理 WP。
- `work_plan_recall_autoworker.py --daemon` 是否启动。
- `runtime/work_plan_recall_worker/worker.log` 是否有错误。

### 结果生成了但页面没显示

检查：

- `工作事务推进驾驶舱_Codex召回结果索引.json` 是否包含同一个 WP 编号。
- `result_html` 是否存在。
- 桌面入口是否从 `GET /api/result?id=WP-...` 轮询。
- 是否仍在用 `file://` 打开页面；完整召回应使用 `http://127.0.0.1:8798/desktop-entry.html`。

### 答案还是旧问题

修复：

- 确认 Codex prompt 使用的是当前 WP 的 `question` 原文。
- 不允许预处理把原文改写成另一个问题。
- 结果文件名和结果索引必须含同一个 WP 编号。

### 重复处理同一条

修复：

- 检查 `worker.lock`。
- 检查队列中同一 WP 是否重复。
- 检查是否同时启动了多个接手器。

## 验收标准

运行：

```bash
python3 outputs/work-cockpit-prototype/validate_work_plan_recall_runtime.py
```

通过标准：

1. 服务脚本存在。
2. 定时接手器存在。
3. 正式收件箱存在。
4. 召回队列存在。
5. 结果索引存在且可解析。
6. 已处理编号能在结果索引中找到。
7. 定时接手器支持 `--daemon`。
8. 定时接手器会调用 `codex exec`。
9. 定时接手器会调用 `complete` 回写。

## 禁止事项

- 禁止在 HTML 里继续堆关键词规则假装智能。
- 禁止只存在浏览器草稿，不写正式收件箱。
- 禁止处理结果只在对话中说完，不回写结果索引。
- 禁止把未处理状态显示成已完成。
- 禁止生成结果但不写 `result_html`。
- 禁止只在聊天里说“处理好了”，却没有进入队列已处理区。
