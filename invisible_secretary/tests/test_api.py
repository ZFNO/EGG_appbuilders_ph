import json
import threading
import unittest
import urllib.request

from invisible_secretary import api


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = api.boot(port=8799)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:8799"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def post(self, path, body=None):
        req = urllib.request.Request(self.base + path, data=json.dumps(body or {}).encode(),
                                     headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req).read())

    def get(self, path):
        return json.loads(urllib.request.urlopen(self.base + path).read())

    def test_end_to_end(self):
        html = urllib.request.urlopen(self.base + "/").read()
        self.assertIn(b"Invisible Secretary", html)

        ev = self.post("/api/route", {"text": "Ask the supplier to confirm today's delivery"})
        self.assertEqual(ev["state"], "awaiting_approval")
        self.assertEqual(len(self.get("/api/nodes")), 3)

        aid = ev["pending_approval"]["approval_id"]
        self.assertEqual(self.post(f"/api/approvals/{aid}/approve")["state"], "succeeded")

        self.assertEqual(
            self.post("/api/route", {"text": "Pay the supplier now, urgently"})["state"],
            "rejected")


if __name__ == "__main__":
    unittest.main(verbosity=2)
