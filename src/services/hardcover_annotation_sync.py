"""
Hardcover annotation spoke.

Push-only: syncs KOReader highlights (drawer=lighten) to Hardcover.app as
user_book_highlights. Only highlights are pushed — underlines and strikeouts
are KOReader rendering annotations with no equivalent concept in a book
tracker's highlight store.

Deletions are propagated: if a local annotation is tombstoned and its
hardcover_highlight_id is set, the remote highlight is deleted.

Book matching re-uses HardcoverDetails already populated by the progress
sync client (hardcover_book_id + hardcover_pages). Books without a Hardcover
match are silently skipped.

Color mapping (KOReader name → Hardcover color string):
  yellow  → yellow
  red     → red
  green   → green
  blue    → blue
  purple  → purple
  orange  → orange
  pink    → pink
  cyan    → cyan
  gray    → gray
  white   → white
(Hardcover accepts free-form color strings; these names match their UI labels.)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from src.api.hardcover_client import HardcoverClient
from src.utils.user_config import resolve_setting

logger = logging.getLogger(__name__)

_MAX_PUSH_PER_CYCLE = 50

# KOReader color → Hardcover color label (free-form strings stored verbatim)
KO_TO_HARDCOVER_COLOR: dict[str, str] = {
    "yellow": "yellow",
    "red": "red",
    "green": "green",
    "blue": "blue",
    "purple": "purple",
    "orange": "orange",
    "pink": "pink",
    "cyan": "cyan",
    "olive": "olive",
    "gray": "gray",
    "white": "white",
}


class HardcoverAnnotationSync:
    """Spoke class — one instance per sync cycle, shared across users."""

    def __init__(self, database_service):
        self._db = database_service

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ko_color_to_hardcover(color: Optional[str]) -> Optional[str]:
        return KO_TO_HARDCOVER_COLOR.get(str(color or "").strip().lower())

    @staticmethod
    def _now_dt() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _truthy(value, default: bool = False) -> bool:
        if value in (None, ""):
            return default
        return str(value).strip().lower() in {"true", "1", "yes", "on"}

    # ------------------------------------------------------------------
    # Book-level resolution
    # ------------------------------------------------------------------

    def _hardcover_details(self, book):
        try:
            return self._db.get_hardcover_details(book.abs_id)
        except Exception:
            return None

    def _hardcover_pages(self, details) -> Optional[int]:
        pages = getattr(details, "hardcover_pages", None)
        return int(pages) if pages else None

    # ------------------------------------------------------------------
    # Push
    # ------------------------------------------------------------------

    def _location_from_pageno(self, pageno: Optional[int], total_pages: Optional[int]) -> Optional[int]:
        if pageno and pageno > 0:
            return pageno
        return None

    def _sync_book(self, user_id, client: HardcoverClient, book) -> bool:
        from src.db.models import KoreaderAnnotation

        details = self._hardcover_details(book)
        if details is None:
            return False
        hardcover_book_id = getattr(details, "hardcover_book_id", None)
        if not hardcover_book_id:
            return False

        # We need user_book.id to attach highlights
        user_book_id = client.get_user_book_id(int(hardcover_book_id))
        if not user_book_id:
            return False

        doc_md5 = str(getattr(book, "kosync_doc_id", "") or "").strip().lower()
        if not doc_md5:
            return False

        did_work = False

        try:
            with self._db.get_session() as session:
                # Deletions first
                tombstone_rows = (
                    session.query(KoreaderAnnotation)
                    .filter(
                        KoreaderAnnotation.md5 == doc_md5,
                        KoreaderAnnotation.user_id == user_id,
                        KoreaderAnnotation.deleted == True,  # noqa: E712
                        KoreaderAnnotation.hardcover_highlight_id != None,  # noqa: E711
                        KoreaderAnnotation.hardcover_synced_at != None,  # noqa: E711
                    )
                    .all()
                )
                now_dt = self._now_dt()
                for row in tombstone_rows:
                    if client.delete_highlight(int(row.hardcover_highlight_id)):
                        row.hardcover_highlight_id = None
                        row.hardcover_synced_at = now_dt
                        did_work = True

                # New highlights (lighten/highlight only — no underlines)
                new_rows = (
                    session.query(KoreaderAnnotation)
                    .filter(
                        KoreaderAnnotation.md5 == doc_md5,
                        KoreaderAnnotation.user_id == user_id,
                        KoreaderAnnotation.deleted == False,  # noqa: E712
                        KoreaderAnnotation.drawer == "lighten",
                        KoreaderAnnotation.hardcover_synced_at == None,  # noqa: E711
                    )
                    .limit(_MAX_PUSH_PER_CYCLE)
                    .all()
                )
                for row in new_rows:
                    if not row.text:
                        continue  # nothing to highlight without the quoted text
                    highlight_id = client.insert_highlight(
                        user_book_id=user_book_id,
                        text=row.text,
                        note=row.note,
                        location=self._location_from_pageno(row.pageno, None),
                        color=self._ko_color_to_hardcover(row.color),
                    )
                    if highlight_id is not None:
                        row.hardcover_highlight_id = highlight_id
                        row.hardcover_synced_at = now_dt
                        did_work = True

                # Edits: note or color changed after initial push
                edit_rows = (
                    session.query(KoreaderAnnotation)
                    .filter(
                        KoreaderAnnotation.md5 == doc_md5,
                        KoreaderAnnotation.user_id == user_id,
                        KoreaderAnnotation.deleted == False,  # noqa: E712
                        KoreaderAnnotation.drawer == "lighten",
                        KoreaderAnnotation.hardcover_highlight_id != None,  # noqa: E711
                        KoreaderAnnotation.hardcover_synced_at < KoreaderAnnotation.updated_at,
                    )
                    .limit(_MAX_PUSH_PER_CYCLE)
                    .all()
                )
                for row in edit_rows:
                    if client.update_highlight(
                        highlight_id=int(row.hardcover_highlight_id),
                        note=row.note,
                        color=self._ko_color_to_hardcover(row.color),
                    ):
                        row.hardcover_synced_at = now_dt
                        did_work = True

                session.commit()
        except Exception as e:
            logger.error(
                "Hardcover annotation sync failed for user %s book %s: %s",
                user_id, getattr(book, "abs_id", "?"), e, exc_info=True,
            )

        return did_work

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def sync_user(self, user_id, creds: dict) -> bool:
        client = HardcoverClient(credentials=creds)
        if not client.is_configured():
            return False

        try:
            books = self._db.get_books_by_status("active") or []
        except Exception as e:
            logger.debug("Hardcover annotation: book enumeration failed for user %s: %s", user_id, e)
            return False

        # Respect per-user book links if the DB exposes them
        try:
            linked = None
            if hasattr(self._db, "get_linked_abs_ids"):
                result = self._db.get_linked_abs_ids(user_id)
                linked = set(result) if result is not None else None
            if linked is not None:
                books = [b for b in books if b.abs_id in linked]
        except Exception:
            pass

        did_work = False
        for book in books:
            try:
                if self._sync_book(user_id, client, book):
                    did_work = True
            except Exception as e:
                logger.error(
                    "Hardcover annotation sync error user %s book %s: %s",
                    user_id, getattr(book, "abs_id", "?"), e,
                )
        return did_work
