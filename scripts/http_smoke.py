"""HTTP integration check. Run only against a disposable account/database.

Required environment: HOURLEAF_TEST_URL, HOURLEAF_TEST_USERNAME,
HOURLEAF_TEST_PASSWORD. The script creates and removes its own work records.
"""

import http.cookiejar
import json
import os
import struct
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = os.environ["HOURLEAF_TEST_URL"].rstrip("/")
USERNAME = os.environ["HOURLEAF_TEST_USERNAME"]
PASSWORD = os.environ["HOURLEAF_TEST_PASSWORD"]
client = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
)
checks = 0


def request(path, method="GET", data=None, csrf=None, headers=None):
    merged = {"Content-Type": "application/json", **(headers or {})}
    if csrf:
        merged["X-CSRFToken"] = csrf
        merged["Origin"] = BASE
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode() if data is not None else None,
        method=method,
        headers=merged,
    )
    try:
        response = client.open(req, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    body = response.read()
    try:
        parsed = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        parsed = None
    return response.status, response.headers, parsed, body


def check(condition, label):
    global checks
    if not condition:
        raise AssertionError(label)
    checks += 1
    print("PASS:", label)


def main():
    status, headers, _, body = request("/")
    check(status == 200 and b"Hourleaf" in body, "frontend HTML served")
    check(
        headers.get("X-Content-Type-Options") == "nosniff",
        "HTML security headers retained",
    )
    check(
        "frame-ancestors 'none'" in headers.get("Content-Security-Policy", ""),
        "content security policy present",
    )
    status, headers, manifest, _ = request("/manifest.webmanifest")
    check(
        status == 200
        and "application/manifest+json" in headers.get("Content-Type", ""),
        "manifest MIME type",
    )
    check(
        manifest["display"] == "standalone" and manifest["start_url"] == "/",
        "standalone Home Screen launch configuration",
    )
    for name, size in [
        ("apple-touch-icon.png", 180),
        ("icon-192.png", 192),
        ("icon-512.png", 512),
    ]:
        status, _, _, body = request("/" + name)
        check(
            status == 200
            and body[:8] == b"\x89PNG\r\n\x1a\n"
            and struct.unpack("!II", body[16:24]) == (size, size),
            f"{name} valid PNG dimensions",
        )
    check(
        request("/assets/missing-file.js")[0] == 404,
        "missing assets fail instead of returning HTML",
    )
    check(request("/api/entries/")[0] == 401, "records require authentication")
    check(
        request(
            "/api/auth/login/", "POST", {"username": USERNAME, "password": PASSWORD}
        )[0]
        == 403,
        "login requires CSRF",
    )
    csrf = request("/api/auth/csrf/")[2]["csrfToken"]
    status, _, account, _ = request(
        "/api/auth/login/", "POST", {"username": USERNAME, "password": PASSWORD}, csrf
    )
    check(
        status == 200 and account["username"] == USERNAME, "session login through Nginx"
    )
    csrf = account["csrfToken"]
    check(
        request("/api/auth/me/")[2]["username"] == USERNAME,
        "session persists between requests",
    )
    kind = "HTTP smoke " + uuid.uuid4().hex[:10]
    entry_ids = []
    try:
        status, _, entry, _ = request(
            "/api/entries/",
            "POST",
            {"date": "2026-09-09", "work_type": kind, "duration": "01:30"},
            csrf,
        )
        check(status == 201 and entry["minutes"] == 90, "duration creation over HTTP")
        entry_ids.append(entry["id"])
        path = f"/api/entries/{entry['id']}/"
        status, _, entry, _ = request(
            path,
            "PUT",
            {
                "date": "2026-09-09",
                "work_type": kind,
                "start_time": "09:00",
                "end_time": "11:00",
            },
            csrf,
        )
        check(status == 200 and entry["minutes"] == 120, "time-range edit over HTTP")
        status, _, _, _ = request(
            "/api/entries/",
            "POST",
            {
                "date": "2026-09-09",
                "work_type": kind,
                "start_time": "10:00",
                "end_time": "12:00",
            },
            csrf,
        )
        check(status == 400, "overlapping range rejected")
        status, _, second, _ = request(
            "/api/entries/",
            "POST",
            {"date": "2026-09-10", "work_type": kind.upper(), "duration": "00:30"},
            csrf,
        )
        check(
            status == 201 and second["work_type"] == kind,
            "work-type canonicalization over HTTP",
        )
        entry_ids.append(second["id"])
        params = urllib.parse.urlencode(
            {"from": "2026-01-01", "to": "2026-12-31", "work_type": kind}
        )
        status, headers, stats, _ = request("/api/analytics/?" + params)
        check(
            status == 200
            and stats["total_minutes"] == 150
            and stats["longest_streak"] == 2,
            "filtered analytics totals and streak",
        )
        check(
            "no-store" in headers.get("Cache-Control", ""),
            "private API responses are not cached",
        )
        check(
            request(path, "PATCH", {"duration": "00:30"})[0] == 403,
            "session writes require CSRF",
        )
        check(
            request("/api/analytics/?from=bad")[0] == 400,
            "invalid dates return validation errors",
        )
    finally:
        for entry_id in entry_ids:
            check(
                request(f"/api/entries/{entry_id}/", "DELETE", csrf=csrf)[0] == 204,
                "test entry deletion",
            )
    check(request("/api/auth/logout/", "POST", csrf=csrf)[0] == 204, "session logout")
    check(request("/api/auth/me/")[0] == 401, "logout removes access")
    print(f"HTTP checks passed: {checks}")


if __name__ == "__main__":
    main()
