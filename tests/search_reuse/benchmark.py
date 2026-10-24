# ruff: noqa: E402, INP001, T201
import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

os.umask(0o077)
p = Path(os.environ["SEARCH_BENCH_WORKDIR"]).resolve()
p.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
# Bypass parser-check registration only; search modules are unmodified.
import types

documents = types.ModuleType("documents")
documents.__path__ = [str(Path(__file__).resolve().parents[2] / "src/documents")]
sys.modules["documents"] = documents
from django.conf import settings

settings.configure(
    SEARCH_LANGUAGE="de",
    ADVANCED_FUZZY_SEARCH_THRESHOLD=None,
    USE_TZ=True,
    TIME_ZONE="Europe/Berlin",
)
import tantivy

from documents.search._backend import SearchMode
from documents.search._backend import TantivyBackend
from documents.search._schema import build_schema
from documents.search._tokenizer import register_tokenizers

a = argparse.ArgumentParser()
a.add_argument("--size", type=int, default=1000)
a.add_argument("--samples", type=int, default=5)
args = a.parse_args()
path = p / f"index-v2-{args.size}"
path.mkdir(exist_ok=True)
schema = build_schema()
index = tantivy.Index(schema, path=str(path))
register_tokenizers(index, "de")
if index.searcher().num_docs != args.size:
    w = index.writer(heap_size=64000000, num_threads=1)
    for i in range(args.size):
        content = f"Synthetic Rechnung Müller Straße übermäßig café alpha beta document reference{i:07d} gemeinsamer Begriff 東京 コーヒー"
        if i == 0:
            content += " uniqueneedle"
        doc = tantivy.Document(
            title=f"Synthetic {i}",
            content=content,
            simple_content=content,
            simple_title=f"Synthetic {i}",
            title_sort=f"{i:07d}",
            notes_text="synthetic alpha note",
        )
        doc.add_unsigned("id", i + 1)
        w.add_document(doc)
    w.commit()
    w.wait_merging_threads()
    index.reload()
b = TantivyBackend(path)
b._raw_index = index
b._raw_schema = schema
rows = []
for mode in [SearchMode.TEXT, SearchMode.QUERY]:
    for q in ["absentneedle", "uniqueneedle", "Rechnung"]:
        expected_ids = b.search_ids(q, None, search_mode=mode)
        expected_hits = b.highlight_hits(q, expected_ids[:25], search_mode=mode)
        for n in range(args.samples + 1):
            for variant in (
                ["baseline", "reuse"] if n % 2 == 0 else ["reuse", "baseline"]
            ):
                t = time.perf_counter()
                prepared = b.prepare_query(q, mode) if variant == "reuse" else None
                t0 = time.perf_counter()
                ids = b.search_ids(q, None, search_mode=mode, prepared_query=prepared)
                t1 = time.perf_counter()
                hits = b.highlight_hits(
                    q,
                    ids[:25],
                    search_mode=mode,
                    prepared_query=prepared,
                )
                t2 = time.perf_counter()
                assert ids == expected_ids and hits == expected_hits
                rows.append(
                    {
                        "mode": mode.value,
                        "q": q,
                        "variant": variant,
                        "sample": n,
                        "phase": "first-use-OS-cache-uncontrolled"
                        if n == 0
                        else "warm",
                        "count": len(ids),
                        "prepare_ms": (t0 - t) * 1000,
                        "search_ids_ms": (t1 - t0) * 1000,
                        "highlight_ms": (t2 - t1) * 1000,
                        "total_ms": (t2 - t) * 1000,
                    },
                )
out = {
    "size": args.size,
    "samples_warm": args.samples,
    "python": sys.version,
    "tantivy": tantivy.__version__,
    "sql": "not initialized; backend-only synthetic benchmark",
    "parity": "all ids and full hit dictionaries exact",
    "rows": rows,
}
(p / f"comparison-{args.size}.json").write_text(json.dumps(out, indent=2))
for mode in ["text", "query"]:
    for q in ["absentneedle", "uniqueneedle", "Rechnung"]:
        for variant in ["baseline", "reuse"]:
            r = [
                x
                for x in rows
                if x["mode"] == mode
                and x["q"] == q
                and x["variant"] == variant
                and x["phase"] == "warm"
            ]
            print(
                mode,
                q,
                variant,
                "hits",
                r[0]["count"],
                {
                    k: round(statistics.median(x[k] for x in r), 3)
                    for k in ["prepare_ms", "search_ids_ms", "highlight_ms", "total_ms"]
                },
            )
