from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase

if TYPE_CHECKING:
    from django.apps.registry import Apps


class TestMigrations(TransactionTestCase):
    @property
    def app(self) -> str:
        return apps.get_containing_app_config(type(self).__module__).name

    migrate_from: Any = None
    dependencies: list[tuple[str, str]] | None = None
    migrate_to: Any = None

    def setUp(self) -> None:
        super().setUp()
        assert self.migrate_from and self.migrate_to, (
            f"TestCase '{type(self).__name__}' must define migrate_from and migrate_to properties"
        )
        self.migrate_from = [(self.app, self.migrate_from)]
        if self.dependencies is not None:
            self.migrate_from.extend(self.dependencies)
        self.migrate_to = [(self.app, self.migrate_to)]
        executor = MigrationExecutor(connection)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        # Reconciliation remains irreversible in production. Historical tests
        # restore its previous constraint only on an empty synthetic test DB.
        reconciliation = ("documents", "0028_lavida_shared_asn")
        if reconciliation in executor.loader.applied_migrations:
            current_apps = executor.loader.project_state().apps
            Document = current_apps.get_model("documents", "Document")
            if Document.objects.exists():
                raise RuntimeError(
                    "Historical migration tests require an empty database",
                )
            old = Document._meta.get_field("archive_serial_number")
            previous = executor.loader.project_state(
                [("documents", "0027_documentbarcode")],
            ).apps.get_model("documents", "Document")
            new = previous._meta.get_field("archive_serial_number").clone()
            new.set_attributes_from_name(old.name)
            new.model = Document
            with connection.schema_editor() as schema_editor:
                schema_editor.alter_field(Document, old, new)
            MigrationRecorder(connection).record_unapplied(*reconciliation)
            executor = MigrationExecutor(connection)

        executor.migrate(self.migrate_from)
        self.setUpBeforeMigration(old_apps)
        self.apps = old_apps
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def setUpBeforeMigration(self, apps: Apps) -> None:
        pass

    def tearDown(self) -> None:
        """Restore the latest schema after every historical migration test."""
        try:
            executor = MigrationExecutor(connection)
            executor.loader.build_graph()
            executor.migrate(executor.loader.graph.leaf_nodes())
        finally:
            super().tearDown()
