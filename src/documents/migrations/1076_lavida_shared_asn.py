"""Reconcile upstream Django state with Lavida's altered historical schema.

Forward only: re-introducing uniqueness could destroy the migration contract.
Historical migrations deliberately remain byte-for-byte upstream.
"""

import django.core.validators
from django.db import migrations
from django.db import models
from django.db.models import Count


def reconcile_schema(apps, schema_editor):
    Document = apps.get_model("documents", "Document")
    Tag = apps.get_model("documents", "Tag")
    alias = schema_editor.connection.alias
    # Fail before any DDL if restoring the missing ownerless-tag index is unsafe.
    if (
        Tag.objects.using(alias)
        .filter(owner__isnull=True)
        .values("name")
        .annotate(n=Count("pk"))
        .filter(n__gt=1)
        .exists()
    ):
        raise RuntimeError(
            "Duplicate ownerless tags: resolve on isolated restore before migration",
        )
    with schema_editor.connection.cursor() as cursor:
        constraints = schema_editor.connection.introspection.get_constraints(
            cursor,
            Document._meta.db_table,
        )
        tag_constraints = schema_editor.connection.introspection.get_constraints(
            cursor,
            Tag._meta.db_table,
        )
    asn_unique = [
        c
        for c in constraints.values()
        if c.get("unique") and c.get("columns") == ["archive_serial_number"]
    ]
    if len(asn_unique) > 1:
        raise RuntimeError(
            "Unexpected multiple ASN unique constraints; manual schema review required",
        )
    if asn_unique:
        old = Document._meta.get_field("archive_serial_number")
        new = old.clone()
        new._unique = False
        new.set_attributes_from_name(old.name)
        new.model = Document
        schema_editor.alter_field(Document, old, new)
    # Legacy historical 1033 omitted this partial unique index. Restore only
    # this known drift, never silently fake the entire migration history.
    if "documents_tag_name_uniq" not in tag_constraints:
        constraint = next(
            c for c in Tag._meta.constraints if c.name == "documents_tag_name_uniq"
        )
        schema_editor.add_constraint(Tag, constraint)


class Migration(migrations.Migration):
    dependencies = [("documents", "1075_workflowaction_order")]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(reconcile_schema)],
            state_operations=[
                migrations.AlterField(
                    model_name="document",
                    name="archive_serial_number",
                    field=models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        db_index=True,
                        validators=[
                            django.core.validators.MaxValueValidator(4294967295),
                            django.core.validators.MinValueValidator(0),
                        ],
                        verbose_name="archive serial number",
                        help_text="The position of this document in your physical document archive.",
                    ),
                ),
            ],
        ),
    ]
