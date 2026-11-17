import json
import threading
import unittest
import urllib.error
import urllib.request

from keren.model import FakeModel
from keren.web import make_server


class Web(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = make_server(FakeModel(), "offline", "fake-offline", port=0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def req(self, path="/api/ask", body=None, headers=None, host=None, method=None):
        h = {"Content-Type": "application/json"}
        h.update(headers or {})
        data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
        r = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), data=data, headers=h, method=method)
        if host:
            r.remove_header("Host")
            r.add_unredirected_header("Host", host)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def ask(self, cid, q):
        code, raw = self.req(body={"customerId": cid, "question": q})
        return code, json.loads(raw)

    def test_page_and_config(self):
        code, raw = self.req("/", method="GET")
        self.assertEqual(code, 200)
        self.assertIn("עוזר תיק השקעות".encode(), raw)
        self.assertEqual(json.loads(self.req("/api/config", method="GET")[1])["mode"], "offline")

    def test_answers(self):
        code, j = self.ask("C-1042", "How much management fee next quarter?")
        self.assertEqual((code, j["status"]), (200, "ok"))
        self.assertIn("$209.02", j["text"])
        self.assertEqual(self.ask("C-1042", "Should the client buy ETH now?")[1]["status"], "refused")
        self.assertEqual(self.ask("C-2000", "value?")[1]["status"], "denied")

    def test_rejects_bad_requests(self):
        self.assertEqual(self.req(body=b"not json")[0], 400)
        self.assertEqual(self.req(body={"customerId": "C-1042"})[0], 400)
        self.assertEqual(self.req(body={"customerId": "C-1042", "question": "x" * 501})[0], 400)
        self.assertEqual(self.req(body={"customerId": "C-1042", "question": "v"},
                                  headers={"Content-Type": "text/plain"})[0], 415)

    def test_rejects_foreign_host_and_origin(self):
        self.assertEqual(self.req("/api/config", method="GET", host="evil.example")[0], 403)
        self.assertEqual(self.req(body={"customerId": "C-1042", "question": "v"},
                                  headers={"Origin": "http://evil.example"})[0], 403)

    def test_operator_cannot_be_chosen_by_client(self):
        code, j = self.ask("C-1042", "value")
        self.assertEqual(code, 200)
        r = self.req(body={"customerId": "C-1042", "question": "value", "operator": "intruder"})
        self.assertEqual(r[0], 200)  # extra field ignored; operator is server-side


if __name__ == "__main__":
    unittest.main()
