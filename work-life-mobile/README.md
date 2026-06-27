# 工作生活计划手机入口

这是“清风显化 · 本身即美 生活本身”的手机独立版发布目录。

手机访问 GitHub Pages 地址后，可以添加到主屏幕使用。任务、每日打卡和勾选完成状态保存在手机浏览器本地。

本目录包含原计划导入文件 `original-work-cockpit-state.json`。

## 公网访问

在 GitHub 仓库打开 Settings -> Pages，Source 选 `Deploy from a branch`，Branch 选 `main`，Folder 选 `/ (root)`。保存后访问：

`https://huangyu4026-create.github.io/four-projects-vault/work-life-mobile/`

## 三人共用轻量云同步

默认不启用云端，仍是手机本机保存。

要让三部手机共用一份数据：

1. 在 Google Drive / Apps Script 新建脚本。
2. 把 `google-apps-script-backend.js` 的内容复制进去。
3. 部署为 Web App，访问权限选“任何拥有链接的人”。
4. 把部署得到的 `/exec` 地址填入 `cloud-config.js`：

```js
window.WORK_LIFE_CLOUD_SYNC_URL = "https://script.google.com/macros/s/xxxxx/exec";
```

这个版本用 Google Apps Script 的脚本属性分块保存一份共享 JSON，不依赖电脑后台，也不依赖 Google Drive 文件。适合三部手机共用轻量计划，并能容纳当前随包带入的原计划内容。
