from datetime import date
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from .models import Entry, WorkType


class ApiEdgeCases(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            "edge-check", password="long-test-password"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def create(self, **overrides):
        payload = {
            "date": "2026-09-09",
            "work_type": "Development",
            "duration": "01:00",
        }
        payload.update(overrides)
        return self.client.post("/api/entries/", payload, format="json")

    def test_login_rejects_non_object_json(self):
        client = APIClient()
        for payload in [[], ["user"], "username", 42, None]:
            with self.subTest(payload=payload):
                response = client.post("/api/auth/login/", payload, format="json")
                self.assertEqual(response.status_code, 400)

    def test_expanding_unicode_type_is_validation_error(self):
        # This ligature expands to many characters under NFKC.
        response = self.create(work_type="ﷺ" * 80)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Entry.objects.count(), 0)

    def test_persian_normalization_and_canonical_spelling(self):
        self.assertEqual(self.create(work_type="كار  پژوهشي").status_code, 201)
        response = self.create(work_type="کار پژوهشی")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["work_type"], "كار پژوهشي")
        self.assertEqual(WorkType.objects.count(), 1)

    def test_private_api_cache_headers(self):
        for url in [
            "/api/auth/me/",
            "/api/entries/",
            "/api/work-types/",
            "/api/analytics/",
        ]:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertIn("no-store", response["Cache-Control"])
                self.assertIn("private", response["Cache-Control"])

    def test_moving_entry_checks_destination_day(self):
        first = self.create(duration="24:00").data
        second = self.create(date="2026-09-10").data
        response = self.client.patch(
            f"/api/entries/{second['id']}/", {"date": "2026-09-09"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Entry.objects.get(pk=second["id"]).date, date(2026, 9, 10))
        response = self.client.patch(
            f"/api/entries/{first['id']}/", {"duration": "23:00"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.client.patch(
                f"/api/entries/{second['id']}/", {"date": "2026-09-09"}, format="json"
            ).status_code,
            200,
        )

    def test_adjacent_ranges_and_midnight(self):
        for start, end in [("00:00", "01:00"), ("01:00", "02:00")]:
            response = self.client.post(
                "/api/entries/",
                {
                    "date": "2026-09-09",
                    "work_type": "Development",
                    "start_time": start,
                    "end_time": end,
                },
                format="json",
            )
            self.assertEqual(response.status_code, 201)
        for start, end in [("00:30", "01:30"), ("23:30", "00:30"), ("10:00", "10:00")]:
            self.assertEqual(
                self.client.post(
                    "/api/entries/",
                    {
                        "date": "2026-09-09",
                        "work_type": "Development",
                        "start_time": start,
                        "end_time": end,
                    },
                    format="json",
                ).status_code,
                400,
            )

    def test_rejected_entry_does_not_create_work_type(self):
        self.create(duration="24:00")
        self.assertEqual(self.create(work_type="Should not exist").status_code, 400)
        self.assertEqual(WorkType.objects.count(), 1)

    def test_pagination_and_owner_fields_cannot_be_forged(self):
        another = get_user_model().objects.create_user("other")
        for day in range(1, 28):
            self.assertEqual(
                self.create(date=f"2026-08-{day:02}", user=another.pk).status_code, 201
            )
        response = self.client.get("/api/entries/")
        self.assertEqual(response.data["count"], 27)
        self.assertEqual(len(response.data["results"]), 25)
        self.assertEqual(
            len(self.client.get("/api/entries/?page=2").data["results"]), 2
        )
        self.assertEqual(Entry.objects.filter(user=another).count(), 0)
        self.assertEqual(self.client.get("/api/entries/?page=999").status_code, 404)

    def test_streak_filters_and_leap_day(self):
        for day in ["2024-02-28", "2024-02-29", "2024-03-01", "2024-03-03"]:
            self.create(date=day, duration="02:00")
        self.create(date="2024-03-03", work_type="Research", duration="01:00")
        response = self.client.get("/api/analytics/?from=2024-01-01&to=2024-12-31")
        self.assertEqual(response.data["longest_streak"], 3)
        self.assertEqual(response.data["active_days"], 4)
        self.assertEqual(response.data["total_minutes"], 540)
        self.assertEqual(response.data["average_minutes"], 135)
        response = self.client.get(
            "/api/analytics/?from=2024-01-01&to=2024-12-31&work_type=research"
        )
        self.assertEqual(response.data["total_minutes"], 60)
        for value in ["20240101", "2024-W01-1", "2024-02-30"]:
            self.assertEqual(
                self.client.get(
                    "/api/analytics/", {"from": value, "to": "2024-12-31"}
                ).status_code,
                400,
            )

    def test_inactive_accounts_cannot_login_or_use_token(self):
        token = Token.objects.create(user=self.user)
        self.user.is_active = False
        self.user.save()
        client = APIClient()
        self.assertEqual(
            client.post(
                "/api/auth/login/",
                {"username": self.user.username, "password": "long-test-password"},
                format="json",
            ).status_code,
            400,
        )
        client.credentials(HTTP_AUTHORIZATION="Token " + token.key)
        self.assertEqual(client.get("/api/entries/").status_code, 401)

    def test_login_throttle(self):
        client = APIClient()
        for _ in range(10):
            self.assertEqual(
                client.post("/api/auth/login/", {}, format="json").status_code, 400
            )
        self.assertEqual(
            client.post("/api/auth/login/", {}, format="json").status_code, 429
        )
