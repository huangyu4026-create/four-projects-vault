(function () {
  const APP_SCRIPT_URLS = [
    "https://script.google.com/macros/s/AKfycbz8MaiJ8h9nfCp0VEXmC0a0WxZ17W7REx_9PtRAP9EU39DWax3V-4Jc-vKwskRO5Wk/exec",
    "https://script.google.com/macros/s/AKfycbxNpxYB2dnufuahisV5PMD-8GbnoHbazsmZsr-SgBLx1-vKD3FBGwQeBdDm9VwEjVt8/exec"
  ];
  const APP_SCRIPT_TOKEN = "";

  const APP_SCRIPT_URL = APP_SCRIPT_URLS[0];
  window.DIGITAL_LIFE_PUBLIC_INBOX_URL = APP_SCRIPT_URL;
  window.DIGITAL_LIFE_PUBLIC_INBOX_URLS = APP_SCRIPT_URLS;
  window.DIGITAL_LIFE_PUBLIC_TOKEN = APP_SCRIPT_TOKEN;

  try {
    const params = new URLSearchParams(location.search);
    if (params.get("cloud")) window.DIGITAL_LIFE_PUBLIC_INBOX_URL = params.get("cloud");
    if (params.get("token")) window.DIGITAL_LIFE_PUBLIC_TOKEN = params.get("token");
  } catch (_) {}
})();
