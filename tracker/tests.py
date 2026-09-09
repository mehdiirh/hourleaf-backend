from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from .models import WorkType


class TrackingTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "alice", password="test-only-very-long-password"
        )
        self.other = get_user_model().objects.create_user(
            "bob", password="test-only-very-long-password"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def create(self, **kwargs):
        return self.client.post(
            "/api/entries/",
            {
                "date": "2026-09-09",
                "work_type": "Development",
                "duration": "02:30",
                **kwargs,
            },
            format="json",
        )

    def test_duration_normalization_and_analytics(self):
        self.assertEqual(self.create().status_code, 201)
        self.assertEqual(self.create(work_type="  DEVELOPMENT ").status_code, 201)
        self.assertEqual(WorkType.objects.count(), 1)
        data = self.client.get("/api/analytics/?from=2026-01-01&to=2026-12-31").data
        self.assertEqual(data["total_minutes"], 300)
        self.assertEqual(data["active_days"], 1)

    def test_owner_isolation_and_authentication(self):
        entry = self.create().data
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get("/api/entries/").data["count"], 0)
        self.assertEqual(self.client.get("/api/work-types/").data, [])
        self.assertEqual(
            self.client.patch(
                f"/api/entries/{entry['id']}/", {"duration": "01:00"}, format="json"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.delete(f"/api/entries/{entry['id']}/").status_code, 404
        )
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/entries/").status_code, 401)

    def test_range_overlap_and_daily_limit(self):
        payload = {
            "date": "2026-09-09",
            "work_type": "Design",
            "start_time": "09:00",
            "end_time": "11:30",
        }
        self.assertEqual(
            self.client.post("/api/entries/", payload, format="json").data["minutes"],
            150,
        )
        self.assertEqual(
            self.client.post("/api/entries/", payload, format="json").status_code, 400
        )
        self.assertEqual(self.create(duration="23:00").status_code, 400)
        self.assertEqual(self.create(duration="00:00").status_code, 400)
        self.assertEqual(self.create(duration="02:99").status_code, 400)
        self.assertEqual(
            self.create(start_time="09:00", end_time="10:00").status_code, 400
        )

    def test_token_and_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertEqual(
            client.post(
                "/api/auth/login/",
                {"username": "alice", "password": "test-only-very-long-password"},
                format="json",
            ).status_code,
            403,
        )
        token = client.get("/api/auth/csrf/").json()["csrfToken"]
        response = client.post(
            "/api/auth/login/",
            {"username": "alice", "password": "test-only-very-long-password"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            client.post("/api/entries/", {}, format="json").status_code, 403
        )
        self.assertEqual(
            client.post(
                "/api/auth/logout/", HTTP_X_CSRFTOKEN=response.data["csrfToken"]
            ).status_code,
            204,
        )
        client.credentials(
            HTTP_AUTHORIZATION="Token " + Token.objects.create(user=self.user).key
        )
        self.assertEqual(
            client.post(
                "/api/entries/",
                {"date": "2026-09-09", "work_type": "API", "duration": "01:00"},
                format="json",
            ).status_code,
            201,
        )

    def test_update_mode_and_range_validation(self):
        entry = self.create().data
        response = self.client.put(
            f"/api/entries/{entry['id']}/",
            {
                "date": "2026-09-09",
                "work_type": "Development",
                "start_time": "13:00",
                "end_time": "14:15",
            },
            format="json",
        )
        self.assertEqual(response.data["minutes"], 75)
        self.assertEqual(
            self.client.patch(
                f"/api/entries/{entry['id']}/", {"duration": "01:00"}, format="json"
            ).data["start_time"],
            None,
        )
        self.assertEqual(
            self.client.get("/api/analytics/?from=invalid").status_code, 400
        )
        self.assertEqual(
            self.client.get(
                "/api/analytics/?from=2020-01-01&to=2026-01-01"
            ).status_code,
            400,
        )
