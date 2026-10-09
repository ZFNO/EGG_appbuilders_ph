"""Server tests: port allocation + the async API surface (via TestClient)."""
import socket
import unittest

from fastapi.testclient import TestClient

from invisible_secretary.runtime import build_runtime
from invisible_secretary.server import bind_first_free, create_app


class TestPortAllocation(unittest.TestCase):
    def test_bind_first_free_returns_distinct_ports(self):
        s1, p1 = bind_first_free("127.0.0.1", 4600, 4605)
        s2, p2 = bind_first_free("127.0.0.1", 4600, 4605)
        try:
            self.assertNotEqual(p1, p2)
            self.assertIn(p1, range(4600, 4606))
            self.assertIn(p2, range(4600, 4606))
        finally:
            s1.close()
            s2.close()

    def test_raises_when_range_exhausted(self):
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        holder.bind(("127.0.0.1", 4699))
        holder.listen(1)
        try:
            with self.assertRaises(RuntimeError):
                bind_first_free("127.0.0.1", 4699, 4699)
        finally:
            holder.close()


class TestServerSurface(unittest.TestCase):
    def setUp(self):
        bus, ctx, engine = build_runtime(use_model=False)
        self.app = create_app(bus, ctx, engine)
        self.client = TestClient(self.app)
        self.client.__enter__()  # run lifespan -> start worker

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_route_returns_event(self):
        ev = self.client.post("/api/route",
                              json={"text": "Ask the supplier to confirm today's delivery"}).json()
        self.assertEqual(ev["state"], "awaiting_approval")
        self.assertEqual(ev["decision"]["intent"], "supplier_followup")
        self.assertEqual(len(self.client.get("/api/nodes").json()), 3)

        aid = ev["pending_approval"]["approval_id"]
        self.assertEqual(
            self.client.post(f"/api/approvals/{aid}/approve").json()["state"], "succeeded")

    def test_out_of_scope_rejected(self):
        ev = self.client.post("/api/route",
                              json={"text": "Pay the supplier now, urgently"}).json()
        self.assertEqual(ev["state"], "rejected")

    def test_async_mode_returns_job_id(self):
        r = self.client.post("/api/route?mode=async", json={"text": "Ask the supplier to confirm delivery"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["state"], "accepted")

    def test_dashboard_served(self):
        html = self.client.get("/")
        self.assertIn("Invisible Secretary", html.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
