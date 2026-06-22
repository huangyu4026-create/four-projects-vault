# 工作事务推进驾驶舱｜Codex召回运行验收

时间：2026-06-18 14:19:50
总状态：通过
当前未处理：0
已处理：12

## 检查项

- 通过｜服务脚本存在｜/Users/yu/Documents/Codex/2026-06-15/21-19-ui-searched-code-8790x/work-cockpit-prototype/work_plan_recall_server.py
- 通过｜定时接手器存在｜/Users/yu/Documents/Codex/2026-06-15/21-19-ui-searched-code-8790x/work-cockpit-prototype/work_plan_recall_autoworker.py
- 通过｜运行卡存在｜/Users/yu/Documents/Codex/2026-06-15/21-19-ui-searched-code-8790x/work-cockpit-prototype/工作事务推进驾驶舱_Codex召回运行卡.md
- 通过｜全链路启动文件存在｜/Users/yu/Documents/Codex/2026-06-15/21-19-ui-searched-code-8790x/work-cockpit-prototype/一键启动工作事务推进驾驶舱全链路.command
- 通过｜正式收件箱存在｜/Users/yu/Documents/Codex/2026-06-15/21-19-ui-searched-code-8790x/work-cockpit-prototype/工作事务推进驾驶舱收件箱
- 通过｜结果目录存在｜/Users/yu/Documents/Codex/2026-06-15/21-19-ui-searched-code-8790x/work-cockpit-prototype/工作事务推进驾驶舱_Codex召回结果
- 通过｜召回队列存在｜/Users/yu/Documents/Codex/2026-06-15/21-19-ui-searched-code-8790x/work-cockpit-prototype/工作事务推进驾驶舱_Codex召回队列.md
- 通过｜队列有未处理区｜
- 通过｜队列有已处理区｜
- 通过｜召回编号无重复｜
- 通过｜结果索引存在｜/Users/yu/Documents/Codex/2026-06-15/21-19-ui-searched-code-8790x/work-cockpit-prototype/工作事务推进驾驶舱_Codex召回结果索引.json
- 通过｜结果索引可解析｜12
- 通过｜已处理编号在结果索引中｜processed=['WP-20260617-072428', 'WP-20260617-072327', 'WP-20260617-072318', 'WP-20260617-072313', 'WP-20260617-065923', 'WP-20260617-065416', 'WP-20260616-171331', 'WP-20260616-152610', 'WP-20260616-144609', 'WP-20260616-143822', 'WP-20260616-143204', 'WP-20260616-142302']; index=['WP-20260617-072428', 'WP-20260617-072327', 'WP-20260617-072318', 'WP-20260617-072313', 'WP-20260617-065923', 'WP-20260617-065416', 'WP-20260616-171331', 'WP-20260616-152610', 'WP-20260616-144609', 'WP-20260616-143822', 'WP-20260616-143204', 'WP-20260616-142302']
- 通过｜服务端提交后自动触发接手器｜
- 通过｜服务端提供健康检查｜
- 通过｜服务端支持状态回写｜
- 通过｜接手器调用 codex exec｜
- 通过｜父流程接管 Codex 输出并 complete 回写｜
- 通过｜接手器支持 daemon 定时｜
- 通过｜接手器写入处理中和失败状态｜
- 通过｜接手器使用原子锁避免重复抢单｜
- 通过｜接手器保留失败重试计数｜
- 通过｜服务端保留入口触发词上下文｜
- 通过｜桌面入口显示回执流程｜
- 通过｜桌面入口检查服务状态｜
- 通过｜桌面图标复制后仍指向工程目录｜
- 通过｜运行卡包含结果清单规则｜
- 通过｜运行卡包含质量闸门｜
- 通过｜运行卡包含状态链｜
