from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from rest_framework.test import APIClient

from .models import Entry, WorkType
from .views import EntryViewSet


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentWritesTests(TransactionTestCase):
    """Run on PostgreSQL: SQLite cannot validate row-lock behavior."""

    def setUp(self):
        self.user = get_user_model().objects.create_user("concurrent-check")

    def run_requests(self, requests):
        barrier = Barrier(len(requests))
        original = EntryViewSet._save

        def synchronized_save(view, serializer):
            # Both serializers see their original rows before either lock is taken.
            barrier.wait(timeout=10)
            return original(view, serializer)

        def send(request):
            close_old_connections()
            client = APIClient()
            client.force_authenticate(get_user_model().objects.get(pk=self.user.pk))
            method, path, data = request
            try:
                return getattr(client, method)(path, data, format="json").status_code
            finally:
                close_old_connections()

        with patch.object(EntryViewSet, "_save", synchronized_save):
            with ThreadPoolExecutor(max_workers=len(requests)) as pool:
                return list(pool.map(send, requests))

    def test_simultaneous_creates_cannot_exceed_daily_limit(self):
        request = (
            "post",
            "/api/entries/",
            {"date": "2026-09-09", "work_type": "Development", "duration": "13:00"},
        )
        self.assertEqual(sorted(self.run_requests([request, request])), [201, 400])
        self.assertEqual(Entry.objects.count(), 1)

    def test_simultaneous_ranges_cannot_overlap(self):
        request = (
            "post",
            "/api/entries/",
            {
                "date": "2026-09-09",
                "work_type": "Development",
                "start_time": "09:00",
                "end_time": "10:00",
            },
        )
        self.assertEqual(sorted(self.run_requests([request, request])), [201, 400])
        self.assertEqual(Entry.objects.count(), 1)

    def test_partial_updates_preserve_both_changes(self):
        work_type = WorkType.objects.create(
            user=self.user, name="Development", normalized_name="development"
        )
        entry = Entry.objects.create(
            user=self.user, work_type=work_type, date="2026-09-09", minutes=60
        )
        path = f"/api/entries/{entry.pk}/"
        self.assertEqual(
            self.run_requests(
                [
                    ("patch", path, {"duration": "02:00"}),
                    ("patch", path, {"work_type": "Research"}),
                ]
            ),
            [200, 200],
        )
        entry.refresh_from_db()
        self.assertEqual(entry.minutes, 120)
        self.assertEqual(entry.work_type.name, "Research")
