import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class BrowserEntryTransportTests(unittest.TestCase):
    def test_public_entry_mirrors_match(self):
        self.assertEqual(
            (ROOT / "digital-life-public" / "index.html").read_text(encoding="utf-8"),
            (ROOT / "dl" / "index.html").read_text(encoding="utf-8"),
        )

    def test_mobile_transport_queues_and_retries_local_copy(self):
        source = (ROOT / "dl" / "index.html").read_text(encoding="utf-8")
        config = (ROOT / "dl" / "cloud-config.js").read_text(encoding="utf-8")
        self.assertIn("yu-digital-life.huangyu4026.chatgpt.site/api/public-inbox", config)
        self.assertIn("isVerifiedRelayUrl", source)
        self.assertIn('transport: "verified"', source)
        self.assertIn("unverified: !data.forwarded", source)
        self.assertIn("本入口采用只写保护", source)
        self.assertIn('submitUrl.searchParams.set("action", "submit")', source)
        self.assertIn("signalImage.src = submitUrl.toString()", source)
        self.assertIn('"pending_unverified", "local_only"', source)
        self.assertNotIn("读取失败，显示本机暂存", source)

    def test_mobile_status_window_tracks_only_local_receipts(self):
        source = (ROOT / "dl" / "index.html").read_text(encoding="utf-8")
        self.assertIn('new URL("/api/public-status", relay.origin)', source)
        self.assertIn('body: JSON.stringify({ ids })', source)
        self.assertIn('resultText', source)
        self.assertIn('云端已收到', source)
        self.assertIn('本地处理中', source)
        self.assertIn('结果已返回', source)
        self.assertIn('window.setInterval', source)
        self.assertIn('}, 30000);', source)
        self.assertIn('upsertLocalItem({', source)
        self.assertNotIn('removeLocalItem(item.id);', source)

    def test_service_worker_cache_version_is_mirrored(self):
        public_worker = (ROOT / "digital-life-public" / "sw.js").read_text(encoding="utf-8")
        short_worker = (ROOT / "dl" / "sw.js").read_text(encoding="utf-8")
        self.assertEqual(public_worker, short_worker)
        self.assertIn("digital-life-public-v7-status-window", public_worker)

    def test_apps_script_mirrors_match_and_preserve_terminal_status(self):
        public_backend = (ROOT / "digital-life-public" / "google-apps-script-backend.js").read_text(encoding="utf-8")
        short_backend = (ROOT / "dl" / "google-apps-script-backend.js").read_text(encoding="utf-8")
        self.assertEqual(public_backend, short_backend)
        self.assertIn('if (action === "submit")', public_backend)
        self.assertIn('"done", "debug_done", "validation_confirmed"', public_backend)
        self.assertIn("terminalStatuses.indexOf(existing.status)", public_backend)


if __name__ == "__main__":
    unittest.main()
