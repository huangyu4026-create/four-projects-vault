// 数字生命公网今日日志入口云端配置。
// 主通道是只写公网中继；Google Apps Script 保留为后备。不要在公网放 OpenAI API key。
window.DIGITAL_LIFE_PUBLIC_INBOX_URL = "https://yu-digital-life.huangyu4026.chatgpt.site/api/public-inbox";
window.DIGITAL_LIFE_PUBLIC_INBOX_URLS = [
  window.DIGITAL_LIFE_PUBLIC_INBOX_URL,
  "https://script.google.com/macros/s/AKfycbz8MaiJ8h9nfCp0VEXmC0a0WxZ17W7REx_9PtRAP9EU39DWax3V-4Jc-vKwskRO5Wk/exec"
];
window.DIGITAL_LIFE_PUBLIC_TOKEN = "";
