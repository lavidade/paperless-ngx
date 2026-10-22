# ruff: noqa: E402, INP001, DJ008
"""Small real-Django regression harness; no customer data or app services.

Loads the actual model field, consumer/serializer methods and migration from source.
Does NOT replace full application/PostgreSQL/UI/OCR integration tests.
Run: python scripts/test_lavida_asn.py
"""

import ast
import importlib.util
import os
import pathlib
import types
import unittest

from django.conf import settings

database = (
    {"ENGINE": "django.db.backends.postgresql", "NAME": os.environ["ASN_TEST_PG"]}
    if os.environ.get("ASN_TEST_PG")
    else {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
)
settings.configure(
    INSTALLED_APPS=[],
    DATABASES={"default": database},
    SECRET_KEY="synthetic-test-only",
    USE_I18N=False,
)
import django

django.setup()
from django.core.validators import MaxValueValidator
from django.core.validators import MinValueValidator
from django.db import connection
from django.db import models
from django.db.migrations.state import ModelState
from django.db.migrations.state import ProjectState
from rest_framework import serializers

ROOT = pathlib.Path(__file__).resolve().parents[1]


def method(path, name, namespace):
    tree = ast.parse((ROOT / path).read_text())
    node = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name
    )
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
            path,
            "exec",
        ),
        namespace,
    )
    return namespace[name]


def field():
    tree = ast.parse((ROOT / "src/documents/models.py").read_text())
    document = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Document"
    )
    node = next(
        n
        for n in document.body
        if isinstance(n, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "archive_serial_number"
            for t in n.targets
        )
    )
    return eval(
        compile(ast.Expression(node.value), "model-field", "eval"),
        {
            "models": models,
            "_": lambda s: s,
            "MaxValueValidator": MaxValueValidator,
            "MinValueValidator": MinValueValidator,
            "ARCHIVE_SERIAL_NUMBER_MIN": 0,
            "ARCHIVE_SERIAL_NUMBER_MAX": 4294967295,
        },
    )


class AsnTests(unittest.TestCase):
    def test_model_and_api_allow_duplicate_asn(self):
        class Doc(models.Model):
            archive_serial_number = field()

            class Meta:
                app_label = "synthetic"

        class Serializer(serializers.ModelSerializer):
            class Meta:
                model = Doc
                fields = ["archive_serial_number"]

        with connection.schema_editor() as editor:
            editor.create_model(Doc)
        try:
            Doc.objects.create(archive_serial_number=42)
            api = Serializer(data={"archive_serial_number": 42})
            self.assertTrue(api.is_valid(), api.errors)
            api.save()
            self.assertEqual(
                list(Doc.objects.values_list("archive_serial_number", flat=True)),
                [42, 42],
            )
            self.assertFalse(Serializer(data={"archive_serial_number": -1}).is_valid())
            self.assertFalse(
                Serializer(data={"archive_serial_number": 4294967296}).is_valid(),
            )
        finally:
            with connection.schema_editor() as editor:
                editor.delete_model(Doc)

    def test_consumer_keeps_range_validation_but_allows_reuse(self):
        class Query:
            def filter(self, **kwargs):
                return self

            def exists(self):
                return True

            def first(self):
                return types.SimpleNamespace(deleted_at=None)

        doc = types.SimpleNamespace(
            ARCHIVE_SERIAL_NUMBER_MIN=0,
            ARCHIVE_SERIAL_NUMBER_MAX=4294967295,
            global_objects=Query(),
        )
        status = types.SimpleNamespace(
            ASN_RANGE="range",
            ASN_ALREADY_EXISTS="unique",
            ASN_ALREADY_EXISTS_IN_TRASH="trash",
        )
        check = method(
            "src/documents/consumer.py",
            "pre_check_asn_value",
            {"Document": doc, "ConsumerStatusShortMessage": status},
        )

        def fail(*args):
            raise ValueError(args)

        for asn in [None, 0, 42, 4294967295]:
            check(
                types.SimpleNamespace(
                    metadata=types.SimpleNamespace(asn=asn),
                    filename="synthetic",
                    _fail=fail,
                ),
            )
        for asn in [-1, 4294967296]:
            with self.assertRaisesRegex(ValueError, "range"):
                check(
                    types.SimpleNamespace(
                        metadata=types.SimpleNamespace(asn=asn),
                        filename="synthetic",
                        _fail=fail,
                    ),
                )

    def test_serializer_does_not_reserve_trashed_asn(self):
        tree = ast.parse((ROOT / "src/documents/serialisers.py").read_text())
        cls = next(
            n
            for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == "DocumentSerializer"
        )
        validate = next(
            (
                n
                for n in cls.body
                if isinstance(n, ast.FunctionDef) and n.name == "validate"
            ),
            None,
        )
        # No override needed once the special trash uniqueness restriction is removed.
        if validate is not None:
            code = ast.unparse(validate)
            self.assertNotIn("Document.deleted_objects.filter", code)

    def test_migration_fresh_and_legacy_schema(self):
        paths = list((ROOT / "src/documents/migrations").glob("*lavida_shared_asn.py"))
        self.assertEqual(len(paths), 1, "explicit reconciliation migration missing")
        spec = importlib.util.spec_from_file_location("asn_migration", paths[0])
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        for legacy in [False, True]:
            with self.subTest(legacy=legacy):
                state = ProjectState()
                state.add_model(
                    ModelState(
                        "documents",
                        "Document",
                        [
                            ("id", models.AutoField(primary_key=True)),
                            (
                                "archive_serial_number",
                                models.PositiveIntegerField(
                                    unique=True,
                                    null=True,
                                    db_index=True,
                                ),
                            ),
                        ],
                    ),
                )
                state.add_model(
                    ModelState(
                        "documents",
                        "Tag",
                        [
                            ("id", models.AutoField(primary_key=True)),
                            ("name", models.CharField(max_length=128)),
                            ("owner", models.IntegerField(null=True)),
                        ],
                        options={
                            "constraints": [
                                models.UniqueConstraint(
                                    fields=["name"],
                                    condition=models.Q(owner__isnull=True),
                                    name="documents_tag_name_uniq",
                                ),
                            ],
                        },
                    ),
                )
                physical = state.clone()
                if legacy:
                    physical.models["documents", "document"].fields[
                        "archive_serial_number"
                    ]._unique = False
                    physical.models["documents", "tag"].options["constraints"] = []
                doc = physical.apps.get_model("documents", "Document")
                tag = physical.apps.get_model("documents", "Tag")
                with connection.schema_editor() as editor:
                    editor.create_model(doc)
                    editor.create_model(tag)
                try:
                    doc.objects.create(archive_serial_number=42)
                    if legacy:
                        doc.objects.create(archive_serial_number=42)
                    with connection.schema_editor() as editor:
                        migration.reconcile_schema(state.apps, editor)
                        migration.reconcile_schema(state.apps, editor)
                    doc.objects.create(archive_serial_number=42)
                    self.assertEqual(
                        doc.objects.filter(archive_serial_number=42).count(),
                        3 if legacy else 2,
                    )
                    with connection.cursor() as cursor:
                        constraints = connection.introspection.get_constraints(
                            cursor,
                            tag._meta.db_table,
                        )
                    self.assertIn("documents_tag_name_uniq", constraints)
                finally:
                    with connection.schema_editor() as editor:
                        editor.delete_model(doc)
                        editor.delete_model(tag)

    def test_migration_updates_django_state(self):
        path = next((ROOT / "src/documents/migrations").glob("*lavida_shared_asn.py"))
        spec = importlib.util.spec_from_file_location("asn_state_migration", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        state = ProjectState()
        state.add_model(
            ModelState(
                "documents",
                "Document",
                [
                    ("id", models.AutoField(primary_key=True)),
                    (
                        "archive_serial_number",
                        models.PositiveIntegerField(unique=True, null=True),
                    ),
                ],
            ),
        )
        for operation in module.Migration.operations:
            operation.state_forwards("documents", state)
        self.assertFalse(
            state.apps.get_model("documents", "Document")
            ._meta.get_field("archive_serial_number")
            .unique,
        )

    def test_barcode_preserves_repeated_asn_even_with_handoff_flag(self):
        if not any(
            isinstance(n, ast.FunctionDef) and n.name == "_apply_detected_asn"
            for n in ast.walk(
                ast.parse((ROOT / "src/documents/barcodes.py").read_text()),
            )
        ):
            self.skipTest("Bridge assigns detected ASN directly")

        class Query:
            def filter(self, **kwargs):
                return self

            def exists(self):
                return True

        apply = method(
            "src/documents/barcodes.py",
            "_apply_detected_asn",
            {
                "Document": types.SimpleNamespace(global_objects=Query()),
                "logger": types.SimpleNamespace(info=lambda *args: None),
            },
        )
        metadata = types.SimpleNamespace(asn=None, skip_asn_if_exists=True)
        apply(types.SimpleNamespace(metadata=metadata), 42)
        self.assertEqual(metadata.asn, 42)


if __name__ == "__main__":
    unittest.main()
