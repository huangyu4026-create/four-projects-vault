# 数字生命公网今日日志入口

这是一个独立的新入口，不替换、不改动现有本地多工程手机录入口。

## 角色

1. 公网页面只负责提交今日日志。
2. Google Apps Script 只负责临时保存云端收件箱。
3. Mac 本地拉取器负责把待处理日志送入现有 `8790 /api/entries` 数字生命入口。
4. 正式入库、AI 深度点评、时空轴和月度库写入，仍由 Mac 上的数字生命主链完成。

## 公网页面

GitHub Pages 发布后访问：

`https://huangyu4026-create.github.io/four-projects-vault/digital-life-public/`

页面只显示：日期、今日日志正文、提交、查看处理结果。

## 云端收件箱部署

1. 打开 Google Apps Script，新建项目。
2. 复制 `google-apps-script-backend.js` 全文进去。
3. 可选：在 Apps Script 项目设置的脚本属性里新增 `DIGITAL_LIFE_PUBLIC_TOKEN` 作为口令。
4. 部署为 Web App，访问权限选“任何拥有链接的人”。
5. 把 `/exec` 地址填入 `cloud-config.js` 的 `DIGITAL_LIFE_PUBLIC_INBOX_URL`，或在页面配置面板里保存。

注意：这里绝对不要填写 OpenAI API key。OpenAI key 只留在 Mac 本地数字生命运行环境里。

## Mac 拉取

先启动现有本地手机入口：

```bash
python3 mobile-intake/server.py
```

然后在本目录复制配置：

```bash
cp config.local.example.env config.local.env
```

把 Apps Script `/exec` 地址和口令填入 `config.local.env`。

手动拉取一次：

```bash
./run_local_pull_once.sh
```

拉取器会把云端 `pending` 的 `today_log` 送入：

`http://127.0.0.1:8790/api/entries`

提交给本地入口的核心字段固定为：

```json
{
  "project": "digital_life",
  "type": "inbox",
  "stage": "今日日志",
  "source": "digital-life-public"
}
```

## 验证

不接真实云端、不写本地工程的演练：

```bash
python3 local-puller.py --cloud-file samples/sample-cloud-inbox.json --dry-run --ack-file /tmp/digital-life-public-ack.json
```
