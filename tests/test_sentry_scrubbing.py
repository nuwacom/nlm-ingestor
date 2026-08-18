import gzip
import io
import json
import os
import sys
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

DOC_TEXT = "CONFIDENTIAL kundennummer 4711 diagnosis lupus"


class _RecordingHandler(BaseHTTPRequestHandler):
    envelopes = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        _RecordingHandler.envelopes.append(body)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


def _events(envelopes):
    events = []
    for body in envelopes:
        lines = body.split(b"\n")
        for i, line in enumerate(lines):
            try:
                item = json.loads(line)
            except ValueError:
                continue
            # envelope item header for an event; the payload is the next line
            if isinstance(item, dict) and item.get("type") == "event":
                events.append(json.loads(lines[i + 1]))
    return events


class SentryScrubbingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _RecordingHandler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        # must be set before the daemon module import below: init runs at import
        os.environ["SENTRY_DSN"] = "http://k@127.0.0.1:%d/1" % cls.server.server_address[1]
        os.environ["SENTRY_ENVIRONMENT"] = "test"
        try:
            import magic  # noqa: F401
        except ImportError:
            # python-magic needs native libmagic; the route under test never
            # reaches it (.pdf short-circuits extract_file_properties)
            stub = types.ModuleType("magic")
            stub.Magic = lambda *args, **kwargs: None
            sys.modules["magic"] = stub
        import nlm_ingestor.ingestion_daemon.__main__ as daemon

        cls.daemon = daemon

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_scrubber_strips_locals_and_request_body_without_dropping_event(self):
        event = {
            "exception": {
                "values": [{"stacktrace": {"frames": [{"function": "f", "vars": {"block_text": DOC_TEXT}}]}}]
            },
            "threads": {
                "values": [{"stacktrace": {"frames": [{"function": "g", "vars": {"vls": [DOC_TEXT]}}]}}]
            },
            "request": {"url": "http://x/api/parseDocument", "data": {"file": DOC_TEXT}},
        }
        scrubbed = self.daemon._scrub_sentry_event(event, {})
        self.assertIsNotNone(scrubbed, "scrubber must never drop the event")
        self.assertNotIn(DOC_TEXT, json.dumps(scrubbed))
        self.assertNotIn("vars", scrubbed["exception"]["values"][0]["stacktrace"]["frames"][0])
        self.assertNotIn("data", scrubbed["request"])
        self.assertEqual(scrubbed["request"]["url"], "http://x/api/parseDocument")

    def test_scrubber_passes_minimal_event_through(self):
        self.assertEqual(self.daemon._scrub_sentry_event({}, {}), {})

    def test_parse_failure_reports_exactly_one_event_without_document_text(self):
        import sentry_sdk

        def boom(doc_name, doc_location, mime_type, parse_options=None):
            block_text = DOC_TEXT  # noqa: F841 - must show up in frame locals
            line_info = {"text": DOC_TEXT}  # noqa: F841
            raise IndexError("string index out of range")

        original = self.daemon.ingestor_api.ingest_document
        self.daemon.ingestor_api.ingest_document = boom
        _RecordingHandler.envelopes = []
        try:
            client = self.daemon.app.test_client()
            resp = client.post(
                "/api/parseDocument",
                data={"file": (io.BytesIO(DOC_TEXT.encode()), "kunde_report.pdf")},
                content_type="multipart/form-data",
            )
        finally:
            self.daemon.ingestor_api.ingest_document = original

        self.assertEqual(resp.status_code, 500)
        sentry_sdk.flush(timeout=10)

        raw = b"".join(_RecordingHandler.envelopes)
        self.assertNotIn(DOC_TEXT.encode(), raw)

        events = _events(_RecordingHandler.envelopes)
        self.assertEqual(len(events), 1, "one failure must produce exactly one Sentry event")
        exc = events[0]["exception"]["values"][-1]
        self.assertEqual(exc["type"], "IndexError")


if __name__ == "__main__":
    unittest.main()
