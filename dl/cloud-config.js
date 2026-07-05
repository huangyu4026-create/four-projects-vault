(function () {
  const APP_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzyVXeA4TQzi937k7Ndv0ALvhhxvgP5OtpBIVPp6GzwsOdRGfXxwWQYi4B0i6O1I1c2/exec";
  const APP_SCRIPT_TOKEN = "";

  window.DIGITAL_LIFE_PUBLIC_INBOX_URL = APP_SCRIPT_URL;
  window.DIGITAL_LIFE_PUBLIC_TOKEN = APP_SCRIPT_TOKEN;

  try {
    const params = new URLSearchParams(location.search);
    if (params.get("cloud")) window.DIGITAL_LIFE_PUBLIC_INBOX_URL = params.get("cloud");
    if (params.get("token")) window.DIGITAL_LIFE_PUBLIC_TOKEN = params.get("token");
  } catch (_) {}
})();
