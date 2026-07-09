"""
Tests for the Hardcover annotation spoke:
  - HardcoverClient highlight mutations (mocked GraphQL)
  - HardcoverAnnotationSync (push, edits, deletions, skip non-highlights)
"""

import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("DATA_DIR", "/tmp/hc_ann_test")


DOC_MD5 = "c" * 32


# ---------------------------------------------------------------------------
# HardcoverClient highlight mutation tests
# ---------------------------------------------------------------------------

class TestHardcoverClientHighlights(unittest.TestCase):
    def _client(self):
        from src.api.hardcover_client import HardcoverClient
        c = HardcoverClient(credentials={"HARDCOVER_TOKEN": "tok", "HARDCOVER_ENABLED": "true"})
        return c

    def test_insert_highlight_success(self):
        c = self._client()
        c.query = MagicMock(return_value={"insert_user_book_highlights_one": {"id": 42}})
        result = c.insert_highlight(user_book_id=1, text="great passage", note="my note", location=10, color="yellow")
        self.assertEqual(result, 42)

    def test_insert_highlight_returns_none_on_failure(self):
        c = self._client()
        c.query = MagicMock(return_value=None)
        result = c.insert_highlight(user_book_id=1, text="text")
        self.assertIsNone(result)

    def test_insert_highlight_returns_none_when_no_id(self):
        c = self._client()
        c.query = MagicMock(return_value={"insert_user_book_highlights_one": {}})
        result = c.insert_highlight(user_book_id=1, text="text")
        self.assertIsNone(result)

    def test_update_highlight_success(self):
        c = self._client()
        c.query = MagicMock(return_value={"update_user_book_highlights_by_pk": {"id": 7}})
        result = c.update_highlight(7, note="updated", color="blue")
        self.assertTrue(result)

    def test_update_highlight_returns_false_on_none(self):
        c = self._client()
        c.query = MagicMock(return_value=None)
        result = c.update_highlight(7)
        self.assertFalse(result)

    def test_delete_highlight_success(self):
        c = self._client()
        c.query = MagicMock(return_value={"delete_user_book_highlights_by_pk": {"id": 5}})
        result = c.delete_highlight(5)
        self.assertTrue(result)

    def test_delete_highlight_failure(self):
        c = self._client()
        c.query = MagicMock(return_value=None)
        result = c.delete_highlight(5)
        self.assertFalse(result)

    def test_get_highlights_returns_list(self):
        c = self._client()
        rows = [{"id": 1, "text": "hi", "note": None, "location": 5, "location_type": "page", "color": "yellow"}]
        c.query = MagicMock(return_value={"user_book_highlights": rows})
        result = c.get_highlights(1)
        self.assertEqual(result, rows)

    def test_get_highlights_none_on_error(self):
        c = self._client()
        c.query = MagicMock(return_value=None)
        result = c.get_highlights(1)
        self.assertIsNone(result)

    def test_get_user_book_id_found(self):
        c = self._client()
        c.get_user_id = MagicMock(return_value=99)
        c.query = MagicMock(return_value={"user_books": [{"id": 55}]})
        result = c.get_user_book_id(10)
        self.assertEqual(result, 55)

    def test_get_user_book_id_not_found(self):
        c = self._client()
        c.get_user_id = MagicMock(return_value=99)
        c.query = MagicMock(return_value={"user_books": []})
        result = c.get_user_book_id(10)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# HardcoverAnnotationSync tests
# ---------------------------------------------------------------------------

def _make_db():
    db = MagicMock()
    db.get_books_by_status.return_value = []
    db.get_linked_abs_ids.return_value = None
    return db


def _make_book(abs_id="abs-1", doc_md5=DOC_MD5):
    b = SimpleNamespace()
    b.abs_id = abs_id
    b.kosync_doc_id = doc_md5
    return b


def _make_ann(
    id=1,
    drawer="lighten",
    color="yellow",
    text="highlighted text",
    note=None,
    pageno=5,
    deleted=False,
    hardcover_highlight_id=None,
    hardcover_synced_at=None,
    updated_at=None,
    ann_datetime="2026-07-01 10:00:00",
):
    a = MagicMock()
    a.id = id
    a.drawer = drawer
    a.color = color
    a.text = text
    a.note = note
    a.pageno = pageno
    a.deleted = deleted
    a.hardcover_highlight_id = hardcover_highlight_id
    a.hardcover_synced_at = hardcover_synced_at
    a.updated_at = updated_at if updated_at is not None else datetime.now(timezone.utc).replace(tzinfo=None)
    a.datetime = ann_datetime
    return a


class TestHardcoverAnnotationSyncColorMapping(unittest.TestCase):
    def setUp(self):
        from src.services.hardcover_annotation_sync import HardcoverAnnotationSync
        self.sync = HardcoverAnnotationSync.__new__(HardcoverAnnotationSync)

    def test_yellow_maps_to_yellow(self):
        self.assertEqual(self.sync._ko_color_to_hardcover("yellow"), "yellow")

    def test_purple_maps_to_purple(self):
        self.assertEqual(self.sync._ko_color_to_hardcover("purple"), "purple")

    def test_unknown_maps_to_none(self):
        self.assertIsNone(self.sync._ko_color_to_hardcover("chartreuse"))

    def test_none_maps_to_none(self):
        self.assertIsNone(self.sync._ko_color_to_hardcover(None))


class TestHardcoverAnnotationSyncPush(unittest.TestCase):
    def _make_sync(self, db=None):
        from src.services.hardcover_annotation_sync import HardcoverAnnotationSync
        return HardcoverAnnotationSync(db or _make_db())

    def _make_session(self, new_rows=None, edit_rows=None, tombstone_rows=None):
        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)

        q = session.query.return_value.filter.return_value

        # Each `.filter()` chain returns a limiter; we mock `.all()` sequentially
        # by tracking call count on `.all()`.
        call_count = [0]
        all_responses = [tombstone_rows or [], new_rows or [], edit_rows or []]

        def side_all():
            idx = call_count[0]
            call_count[0] += 1
            return all_responses[idx] if idx < len(all_responses) else []

        q.all.side_effect = side_all
        q.limit.return_value.all.side_effect = side_all
        return session

    def test_push_new_highlight_calls_insert(self):
        db = _make_db()
        row = _make_ann(id=1)

        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)

        # tombstones, new rows, edit rows
        call_idx = [0]
        batches = [[], [row], []]
        def all_side():
            i = call_idx[0]; call_idx[0] += 1
            return batches[i] if i < len(batches) else []

        session.query.return_value.filter.return_value.all.side_effect = all_side
        session.query.return_value.filter.return_value.limit.return_value.all.side_effect = all_side
        db.get_session.return_value = session

        details = SimpleNamespace(hardcover_book_id=10, hardcover_pages=300)
        db.get_hardcover_details = MagicMock(return_value=details)

        sync = self._make_sync(db)

        client = MagicMock()
        client.is_configured.return_value = True
        client.get_user_book_id.return_value = 55
        client.insert_highlight.return_value = 99

        book = _make_book()
        with patch.object(sync, "_sync_book", wraps=sync._sync_book):
            sync._sync_book(1, client, book)

        client.insert_highlight.assert_called_once_with(
            user_book_id=55,
            text="highlighted text",
            note=None,
            location=5,
            color="yellow",
        )
        self.assertEqual(row.hardcover_highlight_id, 99)

    def test_skips_highlight_without_text(self):
        db = _make_db()
        row = _make_ann(id=2, text=None)

        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        call_idx = [0]
        batches = [[], [row], []]
        def all_side():
            i = call_idx[0]; call_idx[0] += 1
            return batches[i] if i < len(batches) else []
        session.query.return_value.filter.return_value.all.side_effect = all_side
        session.query.return_value.filter.return_value.limit.return_value.all.side_effect = all_side
        db.get_session.return_value = session
        details = SimpleNamespace(hardcover_book_id=10, hardcover_pages=300)
        db.get_hardcover_details = MagicMock(return_value=details)

        sync = self._make_sync(db)
        client = MagicMock()
        client.get_user_book_id.return_value = 55

        book = _make_book()
        sync._sync_book(1, client, book)

        client.insert_highlight.assert_not_called()

    def test_tombstone_calls_delete(self):
        db = _make_db()
        row = _make_ann(id=3, deleted=True, hardcover_highlight_id=77, hardcover_synced_at=datetime.now(timezone.utc).replace(tzinfo=None), updated_at=datetime.now(timezone.utc).replace(tzinfo=None))

        session = MagicMock()
        session.__enter__ = MagicMock(return_value=session)
        session.__exit__ = MagicMock(return_value=False)
        call_idx = [0]
        batches = [[row], [], []]
        def all_side():
            i = call_idx[0]; call_idx[0] += 1
            return batches[i] if i < len(batches) else []
        session.query.return_value.filter.return_value.all.side_effect = all_side
        session.query.return_value.filter.return_value.limit.return_value.all.side_effect = all_side
        db.get_session.return_value = session
        details = SimpleNamespace(hardcover_book_id=10, hardcover_pages=300)
        db.get_hardcover_details = MagicMock(return_value=details)

        sync = self._make_sync(db)
        client = MagicMock()
        client.get_user_book_id.return_value = 55
        client.delete_highlight.return_value = True

        book = _make_book()
        sync._sync_book(1, client, book)

        client.delete_highlight.assert_called_once_with(77)

    def test_skips_book_without_hardcover_details(self):
        db = _make_db()
        db.get_hardcover_details = MagicMock(return_value=None)
        sync = self._make_sync(db)
        client = MagicMock()
        book = _make_book()
        result = sync._sync_book(1, client, book)
        self.assertFalse(result)
        client.insert_highlight.assert_not_called()

    def test_skips_book_without_hardcover_book_id(self):
        db = _make_db()
        details = SimpleNamespace(hardcover_book_id=None, hardcover_pages=300)
        db.get_hardcover_details = MagicMock(return_value=details)
        sync = self._make_sync(db)
        client = MagicMock()
        book = _make_book()
        result = sync._sync_book(1, client, book)
        self.assertFalse(result)

    def test_sync_user_not_configured_skips(self):
        from src.services.hardcover_annotation_sync import HardcoverAnnotationSync
        db = _make_db()
        sync = HardcoverAnnotationSync(db)
        creds = {"HARDCOVER_TOKEN": "", "HARDCOVER_ENABLED": "true"}
        result = sync.sync_user(1, creds)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
