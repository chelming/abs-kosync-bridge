"""Standalone Flask receiver for BookBridge opt-in diagnostics payloads.

Stores diagnostic batches, warning rows, and instance metadata in a
plain SQLite database.  Designed to run in its own Docker container on
port 20129.
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, g, jsonify, request, current_app

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1
_MAX_BODY_BYTES = 1_000_000
_DEFAULT_EXPORT_CAP = 500

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

_DDL = """\
CREATE TABLE IF NOT EXISTS instances (
    instance_id          TEXT PRIMARY KEY,
    first_seen           TEXT NOT NULL,
    last_seen            TEXT NOT NULL,
    last_version         TEXT,
    last_services_json   TEXT,
    last_total_books     INTEGER
);

CREATE TABLE IF NOT EXISTS batches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id  TEXT NOT NULL,
    received_at  TEXT NOT NULL,
    sent_at      TEXT,
    app_version  TEXT,
    services_json TEXT,
    total_books  INTEGER,
    window_start TEXT,
    window_end   TEXT,
    dropped      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS warnings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id     INTEGER NOT NULL REFERENCES batches(id),
    instance_id  TEXT NOT NULL,
    logger       TEXT,
    level        TEXT,
    template     TEXT,
    message      TEXT,
    count        INTEGER NOT NULL DEFAULT 1,
    first_seen   TEXT,
    last_seen    TEXT,
    context_text TEXT
);

CREATE INDEX IF NOT EXISTS idx_warnings_template    ON warnings(template);
CREATE INDEX IF NOT EXISTS idx_warnings_instance    ON warnings(instance_id);
CREATE INDEX IF NOT EXISTS idx_warnings_batch       ON warnings(batch_id);
CREATE INDEX IF NOT EXISTS idx_batches_instance     ON batches(instance_id);
CREATE INDEX IF NOT EXISTS idx_batches_received_at  ON batches(received_at);
"""


def init_db(db_path: str) -> None:
    """Create the schema if it does not already exist (idempotent)."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    with sqlite3.connect(db_path, timeout=10) as conn:
        conn.executescript(_DDL)
    logger.info("Database initialised at %s", db_path)


def _get_db() -> sqlite3.Connection:
    """Return a request-scoped database connection stored on Flask's *g*."""
    if "db" not in g:
        db_path: str = current_app.config["DIAG_DB_PATH"]
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db  # type: ignore[return-value]


def _close_db(exc: BaseException | None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_receiver_app(db_path: Optional[str] = None) -> Flask:
    """Build and return the diagnostics receiver Flask application.

    Parameters
    ----------
    db_path:
        Filesystem path for the SQLite database.  When *None* the value
        is read from the ``DIAG_DB_PATH`` environment variable, falling
        back to ``/data/diagnostics.db``.
    """
    if db_path is None:
        db_path = os.environ.get("DIAG_DB_PATH", "/data/diagnostics.db")

    app = Flask("diagnostics_receiver")
    app.config["DIAG_DB_PATH"] = db_path

    app.teardown_appcontext(_close_db)

    init_db(db_path)

    # -- health ---------------------------------------------------------------
    @app.route("/api/v1/health")
    def health() -> Any:
        db = _get_db()
        inst_count = db.execute("SELECT COUNT(*) FROM instances").fetchone()[0]
        batch_count = db.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
        return jsonify({"ok": True, "instances": inst_count, "batches": batch_count})

    # -- POST diagnostics -----------------------------------------------------
    @app.route("/api/v1/diagnostics", methods=["POST"])
    def receive_diagnostics() -> Any:
        content_length = request.content_length
        if content_length is not None and content_length > _MAX_BODY_BYTES:
            return jsonify({"ok": False, "error": "payload too large"}), 413

        raw = request.get_data(cache=True, as_text=False)
        if len(raw) > _MAX_BODY_BYTES:
            return jsonify({"ok": False, "error": "payload too large"}), 413

        try:
            payload: Dict[str, Any] = request.get_json(force=False, silent=False)
        except Exception:
            return jsonify({"ok": False, "error": "invalid JSON"}), 400

        if payload is None or not isinstance(payload, dict):
            return jsonify({"ok": False, "error": "invalid JSON"}), 400

        if payload.get("schema") != _SCHEMA_VERSION:
            return jsonify({"ok": False, "error": "unsupported schema version"}), 400

        instance_id = payload.get("instance_id", "")
        if not isinstance(instance_id, str) or not instance_id.strip():
            return jsonify({"ok": False, "error": "missing or empty instance_id"}), 400

        warnings_raw: List[Dict[str, Any]] = payload.get("warnings")
        if warnings_raw is None:
            warnings_raw = []
        if not isinstance(warnings_raw, list):
            return jsonify({"ok": False, "error": "warnings must be a list"}), 400

        now_iso = datetime.now(timezone.utc).isoformat()
        services_json = json.dumps(payload.get("services"), separators=(",", ":"))

        try:
            db = _get_db()
            # Upsert instance
            db.execute(
                """\
                INSERT INTO instances (instance_id, first_seen, last_seen,
                                       last_version, last_services_json, last_total_books)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(instance_id) DO UPDATE SET
                    last_seen            = excluded.last_seen,
                    last_version         = excluded.last_version,
                    last_services_json   = excluded.last_services_json,
                    last_total_books     = excluded.last_total_books
                """,
                (
                    instance_id,
                    now_iso,
                    now_iso,
                    payload.get("app_version"),
                    services_json,
                    payload.get("total_books"),
                ),
            )
            # Insert batch
            window = payload.get("window") or {}
            cur = db.execute(
                """\
                INSERT INTO batches
                    (instance_id, received_at, sent_at, app_version, services_json,
                     total_books, window_start, window_end, dropped)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    instance_id,
                    now_iso,
                    payload.get("sent_at"),
                    payload.get("app_version"),
                    services_json,
                    payload.get("total_books"),
                    window.get("start"),
                    window.get("end"),
                    payload.get("dropped", 0),
                ),
            )
            batch_id = cur.lastrowid

            # Insert warnings
            warning_rows: List[Tuple] = []
            for w in warnings_raw:
                ctx = w.get("context")
                if isinstance(ctx, list):
                    context_text = "\n".join(str(c) for c in ctx)
                else:
                    context_text = None
                warning_rows.append((
                    batch_id,
                    instance_id,
                    w.get("logger"),
                    w.get("level"),
                    w.get("template"),
                    w.get("message"),
                    w.get("count", 1),
                    w.get("first_seen"),
                    w.get("last_seen"),
                    context_text,
                ))
            if warning_rows:
                db.executemany(
                    """\
                    INSERT INTO warnings
                        (batch_id, instance_id, logger, level, template,
                         message, count, first_seen, last_seen, context_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    warning_rows,
                )

            db.commit()
            return jsonify({"ok": True, "batch_id": batch_id, "warnings_stored": len(warning_rows)})

        except Exception:
            logger.exception("Unexpected error receiving diagnostics payload")
            return jsonify({"ok": False}), 500

    # -- export ---------------------------------------------------------------
    @app.route("/api/v1/export")
    def export_batches() -> Any:
        since_str = request.args.get("since")
        if since_str:
            since = since_str
        else:
            since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

        db = _get_db()
        rows = db.execute(
            "SELECT * FROM batches WHERE received_at > ? ORDER BY received_at LIMIT ?",
            (since, _DEFAULT_EXPORT_CAP),
        ).fetchall()

        batches: List[Dict[str, Any]] = []
        for row in rows:
            b = dict(row)
            w_rows = db.execute(
                "SELECT * FROM warnings WHERE batch_id = ?", (row["id"],)
            ).fetchall()
            b["warnings"] = [dict(w) for w in w_rows]
            batches.append(b)

        return jsonify({"batches": batches, "generated_at": datetime.now(timezone.utc).isoformat()})

    # -- summary --------------------------------------------------------------
    @app.route("/api/v1/summary")
    def summary() -> Any:
        days_str = request.args.get("days", "7")
        try:
            days = int(days_str)
        except ValueError:
            days = 7
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        db = _get_db()

        # Total batches and warnings in the window
        totals = db.execute(
            """\
            SELECT
                (SELECT COUNT(DISTINCT instance_id) FROM batches WHERE received_at > ?) AS instances,
                (SELECT COUNT(*) FROM batches WHERE received_at > ?) AS batches,
                (SELECT COALESCE(SUM(w.count), 0) FROM warnings w
                 JOIN batches b ON w.batch_id = b.id WHERE b.received_at > ?) AS warnings
            """,
            (since, since, since),
        ).fetchone()

        # Top 50 warning templates
        top_rows = db.execute(
            """\
            SELECT w.template,
                   SUM(w.count) AS total_count,
                   COUNT(DISTINCT w.instance_id) AS distinct_instances,
                   MAX(w.last_seen) AS max_last_seen
            FROM warnings w
            JOIN batches b ON w.batch_id = b.id
            WHERE b.received_at > ?
            GROUP BY w.template
            ORDER BY total_count DESC
            LIMIT 50
            """,
            (since,),
        ).fetchall()

        return jsonify({
            "window_days": days,
            "totals": {
                "instances": totals["instances"],
                "batches": totals["batches"],
                "warnings": totals["warnings"],
            },
            "top_templates": [dict(r) for r in top_rows],
        })

    return app


# ---------------------------------------------------------------------------
# Standalone entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        from waitress import serve as _serve

        _app = create_receiver_app()
        logger.info("Starting diagnostics receiver on 0.0.0.0:20129 (waitress)")
        _serve(_app, host="0.0.0.0", port=20129)
    except ImportError:
        _app = create_receiver_app()
        logger.info("Starting diagnostics receiver on 0.0.0.0:20129 (werkzeug)")
        _app.run(host="0.0.0.0", port=20129)
