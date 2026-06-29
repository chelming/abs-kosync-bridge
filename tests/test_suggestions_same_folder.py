import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.suggestions_service import SuggestionsService


def _build_service() -> SuggestionsService:
    return SuggestionsService(
        database_service=MagicMock(),
        container=MagicMock(),
        manager=MagicMock(),
        get_audiobooks_conditionally=lambda: [],
        get_searchable_ebooks=lambda _q: [],
        audiobook_matches_search=lambda _ab, _q: False,
        get_abs_author=lambda _ab: '',
        logger=MagicMock(),
    )


def _ebook(title: str, path: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=f"{title}.epub",
        title=title,
        authors="Different Author",
        source="Grimmory",
        source_id=f"ebook-{title}",
        path=path,
    )


def test_scan_single_audiobook_scores_same_folder_as_exact_match():
    svc = _build_service()
    candidate_pool = svc._prepare_candidate_pool([
        _ebook("Unrelated Ebook Title", "/books/Alice/Series/Shared Folder/book.epub"),
    ])

    result = svc._scan_single_audiobook(
        {
            "audio_source": "ABS",
            "audio_source_id": "abs-1",
            "audio_title": "Totally Different Audio Title",
            "audio_author": "Different Author",
            "audio_path": "/books/Alice/Series/Shared Folder/audio.m4b",
        },
        candidate_pool,
    )

    assert result is not None
    assert result["matches"][0]["score"] == 100.0
    assert result["matches"][0]["match_reason"] == "same_folder"


def test_same_folder_match_allows_relative_suffix_paths():
    svc = _build_service()
    candidate_pool = svc._prepare_candidate_pool([
        _ebook("Unrelated Ebook Title", "/books/Alice/Series/Shared Folder/book.epub"),
    ])

    result = svc._scan_single_audiobook(
        {
            "audio_source": "ABS",
            "audio_source_id": "abs-1",
            "audio_title": "Totally Different Audio Title",
            "audio_author": "Different Author",
            "audio_path": "Alice/Series/Shared Folder",
        },
        candidate_pool,
    )

    assert result is not None
    assert result["matches"][0]["score"] == 100.0


def test_same_folder_match_ignores_bare_filenames_and_shared_roots():
    svc = _build_service()

    assert not svc._paths_share_parent("audio.m4b", "book.epub")
    assert not svc._paths_share_parent("/books/audio.m4b", "/books/book.epub")
