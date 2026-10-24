# Request-local simple-search query reuse (DEV)

This candidate only avoids rebuilding the simple-text query between ID selection
and page highlighting. It does **not** eliminate the second ranked search, change
text/query semantics, disable highlights or introduce cross-request caching.
The view uses reuse only for `SearchMode.TEXT`; advanced and title search retain
the existing path. Prepared queries are bound to exact input, mode and index
instance. Permission filters and optional advanced filters are reapplied.

## Isolated reproduction

Python 3.12; install `tantivy==0.26.2 whoosh-compat==0.3.0 Django==5.2.13
filelock==4.2.4 pillow==13.0.0 regex==2026.9.29 pytest==9.1.1`.

```sh
python -m pytest -c /dev/null -p no:cacheprovider tests/search_reuse -q
SEARCH_BENCH_WORKDIR=/tmp/search-synthetic python tests/search_reuse/benchmark.py --size 2000 --samples 3
```

The harness bypasses only the documents package's OCR/parser-check bootstrap;
it imports the actual backend, schema, query parser and tokenizers. No database,
application server, OCR, customer data, external service or image publishing is
involved. Start small; enlarge `--size` only within an approved resource budget.
Index writer: one thread, 64 MB heap budget. Use a fresh work directory for a
fresh index. Existing index contents are synthetic. First-use is **not** cold:
OS caches are uncontrolled, and functional reference calls precede samples.
Warm variants alternate order; samples retain all timings in JSON. Independent
phase medians do not necessarily sum to the total median.

Tests assert helper reuse rather than wall-clock thresholds. Parity includes
Unicode, substring matching, punctuation, AND/OR/NOT tokens, phrases, pagination,
score/highlight dictionaries, filters, sorting and permission reapplication.
This standalone suite is not full Django/API integration coverage. Existing
backend CI must also pass. No production speedup is implied by synthetic timing.
No deployment, release, merge or image promotion is authorized by this candidate.
