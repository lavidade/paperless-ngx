"""Lavida contract: ASN identifies a physical group, not a unique document."""

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APITestCase

from documents.models import Document


@override_settings(AUDIT_LOG_ENABLED=False)
class SharedAsnApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="synthetic_asn_admin")
        self.client.force_authenticate(self.user)
        self.first = Document.objects.create(
            title="Synthetic A", checksum="a", archive_serial_number=42,
        )
        self.second = Document.objects.create(title="Synthetic B", checksum="b")

    def test_patch_existing_asn(self):
        response = self.client.patch(
            f"/api/documents/{self.second.pk}/", {"archive_serial_number": 42},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.second.refresh_from_db()
        self.assertEqual(self.second.archive_serial_number, 42)
        self.assertEqual(Document.objects.filter(archive_serial_number=42).count(), 2)

    def test_patch_trashed_asn(self):
        self.first.delete()
        response = self.client.patch(
            f"/api/documents/{self.second.pk}/", {"archive_serial_number": 42},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.second.refresh_from_db()
        self.assertEqual(self.second.archive_serial_number, 42)

    def test_reject_invalid_asn(self):
        for asn in [-1, 4294967296]:
            response = self.client.patch(
                f"/api/documents/{self.second.pk}/", {"archive_serial_number": asn},
            )
            self.assertEqual(response.status_code, 400, response.data)
        self.second.refresh_from_db()
        self.assertIsNone(self.second.archive_serial_number)
