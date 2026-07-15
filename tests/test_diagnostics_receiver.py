"""Tests for the diagnostics_receiver standalone Flask application."""

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from diagnostics_receiver.app import create_receiver_app, init_db


def _valid_payload(**overrides: object) -> dict:
    """Return a fully valid schema-1 diagnostics payload, with overrides."""
    base = {
        "schema": 1,
        "instance_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "sent_at": "2026-07-15T12:00:00+00:00",
        "app_version": "7.2.0",
        "services": {
            "abs": True,
            "kosync": False,
            "storyteller": True,
            "booklore": False,
            "bookfusion": False,
            "book_orbit": True,
            "cwa": False,
            "hardcover": False,
            "storygraph": False,
            "slash_books": True,
        },
        "total_books": 42,
        "window": {
            "start": "2026-07-14T12:00:00+00:00",
            "end": "2026-07-15T12:00:00+00:00",
        },
        "dropped": 0,
        "warnings": [
            {
                "template": "Sync failed after # retries",
                "message": "Sync failed after 3 retries",
                "logger": "src.sync_manager",
                "level": "WARNING",
                "count": 5,
                "first_seen": "2026-07-14T12:00:00+00:00",
                "last_seen": "2026-07-15T11:58:00+00:00",
                "context": ["2026-07-15 11:58:00 WARNING sync_manager.py line 42"],
            },
            {
                "template": "Timeout connecting to #",
                "message": "Timeout connecting to ABS",
                "logger": "src.abs_client",
                "level": "ERROR",
                "count": 2,
                "first_seen": "2026-07-15T10:00:00+00:00",
                "last_seen": "2026-07-15T11:00:00+00:00",
                "context": [
                    "2026-07-15 10:00:00 ERROR abs_client.py line 12",
                    "2026-07-15 10:05:00 ERROR abs_client.py line 12",
                    "2026-07-15 11:00:00 ERROR abs_client.py line 12",
                ],
            },
        ],
    }
    base.update(overrides)
    return base


class TestHealth(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "test.db")
        self._app = create_receiver_app(db_path=self._db_path)
        self._client = self._app.test_client()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_health_returns_zero_counts_on_fresh_db(self) -> None:
        resp = self._client.get("/api/v1/health")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["instances"], 0)
        self.assertEqual(data["batches"], 0)


class TestPostDiagnostics(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "test.db")
        self._app = create_receiver_app(db_path=self._db_path)
        self._client = self._app.test_client()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_valid_payload_returns_200_with_batch_id_and_warnings(self) -> None:
        payload = _valid_payload()
        resp = self._client.post(
            "/api/v1/diagnostics",
            data=json.dumps(payload),
            content_type="application/json",
        )
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["batch_id"], 1)
        self.assertEqual(data["warnings_stored"], 2)

    def test_valid_payload_rows_exist_in_db(self) -> None:
        payload = _valid_payload()
        resp = self._client.post(
            "/api/v1/diagnostics",
            data=json.dumps(payload),
            content_type="application/json",
        )
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            inst = conn.execute(
                "SELECT * FROM instances WHERE instance_id = ?",
                (payload["instance_id"],),
            ).fetchone()
            self.assertIsNotNone(inst)
            self.assertEqual(inst["last_version"], "7.2.0")
            self.assertEqual(inst["last_total_books"], 42)

            batches = conn.execute("SELECT * FROM batches").fetchall()
            self.assertEqual(len(batches), 1)
            self.assertEqual(batches[0]["instance_id"], payload["instance_id"])

            warnings = conn.execute(
                "SELECT * FROM warnings WHERE batch_id = ?", (data["batch_id"],)
            ).fetchall()
            self.assertEqual(len(warnings), 2)

    def test_context_text_is_newline_joined(self) -> None:
        payload = _valid_payload()
        resp = self._client.post(
            "/api/v1/diagnostics",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            warning = conn.execute(
                "SELECT context_text FROM warnings WHERE template = ?",
                ("Timeout connecting to #",),
            ).fetchone()
            self.assertIn("\n", warning["context_text"])
            self.assertEqual(warning["context_text"].count("\n"), 2)

    def test_second_batch_same_instance_upserts(self) -> None:
        p1 = _valid_payload()
        resp1 = self._client.post(
            "/api/v1/diagnostics",
            data=json.dumps(p1),
            content_type="application/json",
        )
        self.assertEqual(resp1.status_code, 200)

        p2 = _valid_payload(app_version="7.3.0", total_books=50)
        resp2 = self._client.post(
            "/api/v1/diagnostics",
            data=json.dumps(p2),
            content_type="application/json",
        )
        self.assertEqual(resp2.status_code, 200)

        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Instance still exactly one row
            inst_count = conn.execute("SELECT COUNT(*) FROM instances").fetchone()[0]
            self.assertEqual(inst_count, 1)

            inst = conn.execute(
                "SELECT * FROM instances WHERE instance_id = ?",
                (p1["instance_id"],),
            ).fetchone()
            self.assertEqual(inst["last_version"], "7.3.0")
            self.assertEqual(inst["last_total_books"], 50)

            batches = conn.execute("SELECT * FROM batches").fetchall()
            self.assertEqual(len(batches), 2)

    def test_rejects_non_json_body(self) -> None:
        resp = self._client.post(
            "/api/v1/diagnostics",
            data="not json at all",
            content_type="text/plain",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.get_json()["ok"])

    def test_rejects_schema_not_one(self) -> None:
        payload = _valid_payload(schema=2)
        resp = self._client.post(
            "/api/v1/diagnostics",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_rejects_missing_instance_id(self) -> None:
        payload = _valid_payload()
        del payload["instance_id"]
        resp = self._client.post(
            "/api/v1/diagnostics",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_rejects_empty_instance_id(self) -> None:
        payload = _valid_payload(instance_id="   ")
        resp = self._client.post(
            "/api/v1/diagnostics",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_rejects_body_over_1mb(self) -> None:
        big = "x" * 1_000_001
        resp = self._client.post(
            "/api/v1/diagnostics",
            data=big,
            content_type="application/octet-stream",
        )
        self.assertEqual(resp.status_code, 413)

    def test_warnings_missing_defaults_to_empty_list(self) -> None:
        payload = _valid_payload(warnings=[])
        resp = self._client.post(
            "/api/v1/diagnostics",
            data=json.dumps(payload),
            content_type="application/json",
        )
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data["warnings_stored"], 0)


class TestExport(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "test.db")
        self._app = create_receiver_app(db_path=self._db_path)
        self._client = self._app.test_client()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_export_returns_batches_with_warnings(self) -> None:
        p = _valid_payload()
        self._client.post(
            "/api/v1/diagnostics",
            data=json.dumps(p),
            content_type="application/json",
        )
        resp = self._client.get("/api/v1/export?since=2020-01-01T00:00:00Z")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(data["batches"]), 1)
        self.assertEqual(len(data["batches"][0]["warnings"]), 2)
        self.assertIn("generated_at", data)

    def test_export_since_future_returns_empty(self) -> None:
        p = _valid_payload()
        self._client.post(
            "/api/v1/diagnostics",
            data=json.dumps(p),
            content_type="application/json",
        )
        resp = self._client.get("/api/v1/export?since=2099-01-01T00:00:00Z")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(data["batches"]), 0)

    def test_export_default_since_is_7_days(self) -> None:
        p = _valid_payload()
        self._client.post(
            "/api/v1/diagnostics",
            data=json.dumps(p),
            content_type="application/json",
        )
        # Default since = 7 days ago; our payload was just posted so it should appear
        resp = self._client.get("/api/v1/export")
        data = resp.get_json()
        self.assertEqual(len(data["batches"]), 1)


class TestSummary(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "test.db")
        self._app = create_receiver_app(db_path=self._db_path)
        self._client = self._app.test_client()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_summary_aggregates_templates_across_instances(self) -> None:
        template = "Sync failed after # retries"
        # Post from instance A
        p_a = _valid_payload(
            instance_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            warnings=[{"template": template, "count": 3}],
        )
        self._client.post(
            "/api/v1/diagnostics",
            data=json.dumps(p_a),
            content_type="application/json",
        )
        # Post from instance B
        p_b = _valid_payload(
            instance_id="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            warnings=[{"template": template, "count": 7}],
        )
        self._client.post(
            "/api/v1/diagnostics",
            data=json.dumps(p_b),
            content_type="application/json",
        )

        resp = self._client.get("/api/v1/summary?days=30")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data["totals"]["instances"], 2)
        self.assertGreaterEqual(len(data["top_templates"]), 1)
        top = data["top_templates"][0]
        self.assertEqual(top["template"], template)
        self.assertEqual(top["total_count"], 10)
        self.assertEqual(top["distinct_instances"], 2)


class TestUnexpectedException(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmpdir, "test.db")
        self._app = create_receiver_app(db_path=self._db_path)
        self._client = self._app.test_client()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_unexpected_exception_returns_500(self) -> None:
        """Monkeypatch _get_db to raise, simulating an unexpected failure."""
        from diagnostics_receiver import app as mod

        original_get_db = mod._get_db

        def _explode():
            raise RuntimeError("simulated DB failure")

        mod._get_db = _explode  # type: ignore[assignment]
        try:
            resp = self._client.post(
                "/api/v1/diagnostics",
                data=json.dumps(_valid_payload()),
                content_type="application/json",
            )
            self.assertEqual(resp.status_code, 500)
            self.assertFalse(resp.get_json()["ok"])
        finally:
            mod._get_db = original_get_db  # type: ignore[assignment]


if __name__ == "__main__":
    unittest.main()
