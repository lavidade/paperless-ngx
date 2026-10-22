"""Exercise a recorded legacy history, not just the current model schema."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.test import TransactionTestCase


class LegacyAsnMigrationTests(TransactionTestCase):
    def test_applied_legacy_migrations_with_shared_asn(self):
        if connection.vendor != "postgresql":
            self.skipTest(
                "Production migration contract is PostgreSQL; SQLite rebuilds have different semantics",
            )
        self.assertTrue(connection.settings_dict["NAME"].startswith("test_"), "Synthetic test database required")
        executor = MigrationExecutor(connection)
        target = executor.loader.graph.leaf_nodes()
        old = [("documents", "1046_workflowaction_remove_all_correspondents_and_more")]
        # Rebuild only this synthetic test database to the old frontier. Never
        # reverse the intentionally irreversible Lavida migration.
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA public CASCADE")
            cursor.execute("CREATE SCHEMA public")
        executor = MigrationExecutor(connection)
        executor.loader = MigrationLoader(connection, replace_migrations=False)
        executor.migrate(old)
        state = executor.loader.project_state(old)
        Document = state.apps.get_model("documents", "Document")
        Tag = state.apps.get_model("documents", "Tag")
        try:
            with connection.schema_editor() as editor:
                field = Document._meta.get_field("archive_serial_number")
                new = field.clone()
                new._unique = False
                new.set_attributes_from_name(field.name)
                new.model = Document
                editor.alter_field(Document, field, new)
                editor.remove_constraint(
                    Tag,
                    next(
                        c
                        for c in Tag._meta.constraints
                        if c.name == "documents_tag_name_uniq"
                    ),
                )
            for checksum in ["legacy-a", "legacy-b"]:
                Document.objects.create(
                    checksum=checksum,
                    archive_serial_number=42,
                    mime_type="application/pdf",
                )
            executor = MigrationExecutor(connection)
            executor.migrate(target)
            current = executor.loader.project_state(target).apps.get_model(
                "documents", "Document",
            )
            self.assertEqual(
                current.objects.filter(archive_serial_number=42).count(), 2,
            )
            current.objects.create(
                checksum="legacy-c",
                archive_serial_number=42,
                mime_type="application/pdf",
            )
            self.assertEqual(
                current.objects.filter(archive_serial_number=42).count(), 3,
            )
        finally:
            MigrationExecutor(connection).migrate(target)
