# 数字生命2.0｜2026-07-22 实施回执

## 结论

- M0 真源、入口、备份、稳定快照与设计冻结：PASS。
- M1 活记忆：PASS。20条记忆，25个版本，5条真实修订链。
- M2 可反证个人模型：PASS。10条假说，12个版本，2条经审计缩小或保留争议。
- M3 真人校准：运行能力已完成；已封存1题，等待自然对话中的本人原话，当前0题完成，未伪造。
- M4 P05/LWG对接：包、自动来源清单、文件哈希、授权门和幂等回执已完成；等待新协议下的真实请求，当前0包0回执。
- M5、M6：保持禁用，需要独立授权。

## 数据库验收

- 正式库 SHA-256：`173fbd446b42ad96618ed3e84723a8cfe3f47732d8504168e4477cb200e72df2`
- 迁移前备份 SHA-256：`30e4cc677fcae030305fd841d066504c32e123fa04746a2cdaa364c49794bd07`
- 稳定快照 SHA-256：`b019327c03573f05b45d007b252fb5808fe9fa82c3ad8d68da6ad1729f19e653`
- `quick_check=ok`；DL2新增表外键违例为0。
- 全库19条旧外键问题与迁移前备份逐行一致，本次未新增。

## 回归与界面

- N01—N15、M4来源与哈希门禁及数据库完整性共22项，22/22通过。
- 真实HTTP服务验证通过：状态、记忆、假说接口均可读。
- 操作台已增加活记忆、模型与反证、校准进度、跨工程包与回执四个只读视图。

## M4 协议加固与旧调用审计

- 上下文包的`source_manifest`改为由P01根据当前记忆版本及证据链自动生成，不接受请求方自报来源。
- 回执必须携带`package_hash`；系统会重算文件规范化哈希，拒绝篡改文件、包外对象和没有`actual_read`的`ACCEPTED`回执。
- 当前联邦接收方已核定为`AI_CONTEXT`，正式名称为“AI上下文八面＋人物专页联邦载入系统”，授权号为`COEX-AI-CONTEXT-DL-20260722`。旧LWG工具不再写作现行接收方。
- P05 REAL-004及其旧LWG下游使用经证据哈希核定为`REAL_PRE_DL2_NOT_COUNTED`：真实存在，但无P01签发的`dlctx`包和DL2回执，不倒签计入M4。
- 回归报告：`reports/169_dl2_validation_20260722.json`，SHA-256 `30a46f89ba2e42cb803a0167634dba81ec51b6deb14c4d7588cedbbcf52eec9a`。
- 旧调用审计：`reports/170_pre_dl2_cross_project_call_audit.json`，SHA-256 `86955c305b948c9eece15fe9b73726359258ec50cc02df434735cdf7d0461138`。

## 回退点

`runtime/backups/digital_life_os_core.pre_dl2_v1_20260722.sqlite`

回退只需停止服务后以该备份恢复正式库；原始日记、Notion母本和现有事实表未被改写。

## GitHub 同步

- 分支：`agent/digital-life-2-20260722`
- 草稿 PR：<https://github.com/huangyu4026-create/four-projects-vault/pull/1>
- 数据库 Release：<https://github.com/huangyu4026-create/four-projects-vault/releases/tag/digital-life-2.0.0-20260722>
- 用户已明确授权上传原始数据与数据库；仍排除令牌、密码、`.env`、WAL/SHM和缓存。
