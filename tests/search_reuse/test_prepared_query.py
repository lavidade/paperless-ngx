# ruff: noqa: E402, INP001
"""Run without Django application bootstrap: pytest -c /dev/null tests/search_reuse."""

import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest
import tantivy
from django.conf import settings

SRC = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SRC))
if not settings.configured:
    settings.configure(
        SEARCH_LANGUAGE="de",
        ADVANCED_FUZZY_SEARCH_THRESHOLD=None,
        USE_TZ=True,
        TIME_ZONE="Europe/Berlin",
    )
# Avoid registering OCR/parser system checks; execute the real search modules.
if "documents" not in sys.modules:
    package = types.ModuleType("documents")
    package.__path__ = [str(SRC / "documents")]
    sys.modules["documents"] = package

from documents.search._backend import SearchMode
from documents.search._backend import TantivyBackend
from documents.search._schema import build_schema
from documents.search._tokenizer import register_tokenizers


@pytest.fixture
def backend(tmp_path):
    b = TantivyBackend(tmp_path)
    b._raw_schema = build_schema()
    b._raw_index = tantivy.Index(b._schema, path=str(tmp_path))
    register_tokenizers(b._index, "de")
    writer = b._index.writer(heap_size=16000000, num_threads=1)
    texts = [
        "alpha beta Müller Straße café medizin-history 東京",
        "alphabet beta gamma",
        "beta alpha übermäßig",
        "other punctuation: a-b 16 6",
    ]
    for i, text in enumerate(texts, 1):
        doc = tantivy.Document(
            title=f"Synthetic {i}",
            content=text,
            simple_title=f"Synthetic {i}",
            simple_content=text,
            notes_text="alpha note",
        )
        doc.add_unsigned("id", i)
        writer.add_document(doc)
    writer.commit()
    writer.wait_merging_threads()
    b._index.reload()
    return b


def test_prepared_query_avoids_second_regex_compilation(backend):
    with patch.object(backend, "_parse_query", wraps=backend._parse_query) as parse:
        prepared = backend.prepare_query("alpha", SearchMode.TEXT)
        ids = backend.search_ids(
            "alpha", None, search_mode=SearchMode.TEXT, prepared_query=prepared,
        )
        hits = backend.highlight_hits(
            "alpha", ids[:2], search_mode=SearchMode.TEXT, prepared_query=prepared,
        )
        assert [hit["id"] for hit in hits] == ids[:2]
        assert parse.call_count == 1


@pytest.mark.parametrize("mode", list(SearchMode))
@pytest.mark.parametrize(
    "query",
    [
        "alpha",
        "pha",
        "Müller",
        "MÜLLER",
        "café",
        "Straße",
        "東京",
        "alpha beta",
        "alpha AND beta",
        "alpha OR gamma",
        "alpha NOT beta",
        '"alpha beta"',
        "medizin-history",
        "a-b",
        "6",
        "absent",
    ],
)
def test_exact_baseline_parity(backend, mode, query):
    prepared = backend.prepare_query(query, mode)
    baseline_ids = backend.search_ids(query, None, search_mode=mode)
    reused_ids = backend.search_ids(
        query, None, search_mode=mode, prepared_query=prepared,
    )
    assert reused_ids == baseline_ids
    for offset in (0, 1, 3):
        page = baseline_ids[offset : offset + 2]
        baseline = backend.highlight_hits(
            query, page, search_mode=mode, rank_start=offset + 1,
        )
        reused = backend.highlight_hits(
            query,
            page,
            search_mode=mode,
            rank_start=offset + 1,
            prepared_query=prepared,
        )
        assert reused == baseline  # includes exact score, order, rank and HTML


def test_prepared_query_rejects_other_source_mode_or_index(backend, tmp_path):
    prepared = backend.prepare_query("alpha", SearchMode.TEXT)
    for query, mode in [("beta", SearchMode.TEXT), ("alpha", SearchMode.QUERY)]:
        with pytest.raises(ValueError, match="does not match"):
            backend.search_ids(query, None, search_mode=mode, prepared_query=prepared)
    other = TantivyBackend(tmp_path / "other")
    other._raw_schema = backend._schema
    other._raw_index = tantivy.Index(backend._schema)
    register_tokenizers(other._index, "de")
    with pytest.raises(ValueError, match="does not match"):
        other.search_ids(
            "alpha", None, search_mode=SearchMode.TEXT, prepared_query=prepared,
        )


def test_permissions_are_not_reused(backend):
    from types import SimpleNamespace

    from documents.search._backend import build_permission_filter

    writer = backend._index.writer(heap_size=16000000, num_threads=1)
    doc = tantivy.Document(content="alpha secret", simple_content="alpha secret")
    doc.add_unsigned("id", 99)
    doc.add_unsigned("owner_id", 123)
    writer.add_document(doc)
    writer.commit()
    writer.wait_merging_threads()
    backend._index.reload()
    prepared = backend.prepare_query("alpha", SearchMode.TEXT)
    with patch.object(
        backend,
        "_build_permission_filter",
        side_effect=lambda u: build_permission_filter(backend._schema, u),
    ):
        owner = backend.search_ids(
            "alpha",
            SimpleNamespace(pk=123),
            search_mode=SearchMode.TEXT,
            prepared_query=prepared,
        )
        other = backend.search_ids(
            "alpha",
            SimpleNamespace(pk=456),
            search_mode=SearchMode.TEXT,
            prepared_query=prepared,
        )
    assert 99 in owner
    assert 99 not in other


def test_filter_query_and_sort_parity(backend):
    prepared = backend.prepare_query("alpha", SearchMode.TEXT)
    kwargs = dict(
        search_mode=SearchMode.TEXT,
        filter_query="beta",
        sort_field="title",
        sort_reverse=True,
        limit=2,
    )
    assert backend.search_ids("alpha", None, **kwargs) == backend.search_ids(
        "alpha", None, prepared_query=prepared, **kwargs,
    )
