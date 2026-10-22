# Shared archive serial numbers

This fork permits several documents to share an archive serial number (ASN).
ASN is not a unique document identifier. Range validation remains unchanged:
values from 0 through 4294967295 are valid; negative values and overflow are not.

## Application behavior

- The model retains an indexed, nullable ASN field without uniqueness.
- REST validation, including documents in the trash, permits repeated ASNs.
- The consumer preserves range validation without rejecting an existing ASN.
- On the v3 branch, barcode metadata handoff retains repeated detected ASNs.

## Schema compatibility

Upstream historical migrations are preserved. A new reconciliation migration
uses database introspection and `SeparateDatabaseAndState` to support both a
fresh upstream schema and a legacy schema without the ASN uniqueness constraint.
The migration removes that constraint only when present, reconciles Django's
field state, and restores the ownerless-tag name constraint only after checking
for duplicates. It never renumbers or deletes ASNs or silently deduplicates tags.

The 2.20 branch adds migration `1076_lavida_shared_asn` after upstream 1075;
the v3 branch adds `0028_lavida_shared_asn` after upstream 0027. Follow the
[upstream v3 migration guide](https://github.com/paperless-ngx/paperless-ngx/blob/v3.3.3/docs/migration-v3.md),
including the required 2.20.15 intermediate version. These forward schema
changes are intentionally irreversible; a downgrade requires a consistent backup.

## Synthetic regression coverage

The tests use synthetic values such as ASN 42, not customer documents:

- `src/documents/tests/test_lavida_asn.py`: REST reuse and range validation.
- `src/documents/tests/test_consumer.py`: consumer ASN validation and, where
  applicable, barcode metadata handoff.
- `src/documents/tests/test_lavida_asn_migrations.py` on the 2.20 branch:
  PostgreSQL migration-recorder history with synthetic legacy schema drift.
- `scripts/test_lavida_asn.py`: isolated Django field/method/schema harness;
  SQLite by default, or a dedicated synthetic PostgreSQL database selected by
  `ASN_TEST_PG`.

Run the harness from the repository root with the test dependencies installed:

```sh
python scripts/test_lavida_asn.py
```

These tests do not establish full upgrade, OCR, optical barcode recognition,
UI, import/export or performance acceptance. No deployment is performed here.
The candidate workflow runs synthetic regression checks before publishing
run/attempt-specific image tags; it does not publish stable release tags.
