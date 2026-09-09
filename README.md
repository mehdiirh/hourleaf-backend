# Hourleaf backend

Private, self-hosted time tracking with Django 5.2, Django REST Framework and PostgreSQL. The React frontend lives in the separate `../frontend` Git repository. Each account sees only its own records and work types. There is no public registration endpoint or signup page.

## Run the whole app with Docker Compose

Keep the repositories side by side as `backend/` and `frontend/`. The Compose file lives here so it is versioned with the backend.

```sh
cp .env.example .env
# Edit .env: replace DJANGO_SECRET_KEY and POSTGRES_PASSWORD with random secrets.
# Generate each with: python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
docker compose up --build -d
docker compose exec backend python manage.py createsuperuser
```

Open http://localhost:8080 and sign in with the created account. Use http://localhost:8080/admin/ to pre-create more users. Regular accounts do not need staff or superuser status. Work entries are deliberately not registered in the shared Django admin.

Compose starts PostgreSQL, runs migrations, collects Django admin assets, starts Gunicorn, and serves the frontend through Nginx. Only Nginx is exposed; the database and backend stay on the internal network. Data persists in named volumes. `docker compose down` preserves it; adding `-v` deletes the data.

### Change the host port

Edit `backend/.env`:

```dotenv
APP_PORT=9090
```

Apply the configuration with `docker compose up -d` from this directory, then open `http://localhost:9090`. No image rebuild is needed. The frontend container continues to listen on port 80; Django and PostgreSQL remain internal. The default localhost CSRF origin uses `${APP_PORT}` automatically. If you configured a custom domain/origin, update its port in `DJANGO_CSRF_TRUSTED_ORIGINS` too.

The default bind is localhost. For access from another machine set `APP_BIND=0.0.0.0`, set your hostname in `DJANGO_ALLOWED_HOSTS` (keep `localhost` for the health check), and set the exact browser origin in `DJANGO_CSRF_TRUSTED_ORIGINS`. For HTTPS through your own reverse proxy, set `COOKIE_SECURE=true` and use an HTTPS trusted origin. HTTPS is needed when sending passwords or API tokens over a network. No hosting provider or cloud deployment configuration is included.

To update after source changes, run `docker compose up --build -d`. Back up before schema changes:

```sh
docker compose exec -T db pg_dump -U worklog worklog > hourleaf-backup.sql
# Restore into an empty database:
# docker compose exec -T db psql -U worklog worklog < hourleaf-backup.sql
```

## Local development

Python 3.14 is used in the Docker image. Local development defaults to SQLite; Compose uses PostgreSQL.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DJANGO_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
export DJANGO_DEBUG=true
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

Then run the frontend development server as described in its README. Settings read environment variables directly; `.env` is loaded by Compose, not automatically by Django.

## API

All record, suggestion and analytics endpoints require authentication. Browser login uses HTTP-only session cookies with CSRF protection, including the login request. Integrations use an administrator-issued token:

```sh
docker compose exec backend python manage.py api_token YOUR_USERNAME
# Invalidate an old token and issue a replacement:
docker compose exec backend python manage.py api_token YOUR_USERNAME --rotate
# Revoke access:
docker compose exec backend python manage.py api_token YOUR_USERNAME --revoke
```

Treat token output as a password. Set `HOURLEAF_TOKEN` in your client environment, then:

```sh
curl http://localhost:8080/api/entries/ \
  -H "Authorization: Token $HOURLEAF_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"date":"2026-09-09","work_type":"Development","duration":"02:30"}'

curl http://localhost:8080/api/entries/ \
  -H "Authorization: Token $HOURLEAF_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"date":"2026-09-09","work_type":"Research","start_time":"14:00","end_time":"15:15"}'
```

| Endpoint | Methods | Purpose |
| --- | --- | --- |
| `/api/auth/csrf/` | GET | Get CSRF cookie and `csrfToken` |
| `/api/auth/login/` | POST | Username/password login, requires `X-CSRFToken`; returns rotated token |
| `/api/auth/logout/` | POST | End browser session |
| `/api/auth/me/` | GET | Current account |
| `/api/entries/` | GET, POST | Paginated records; create an entry |
| `/api/entries/{id}/` | GET, PUT, PATCH, DELETE | Read, replace, update or delete your entry |
| `/api/work-types/?q=dev` | GET | Your work types, ordered by frequency; up to 100 |
| `/api/analytics/?from=2026-01-01&to=2026-12-31` | GET | Daily totals, category totals, active-day average and longest streak |

List parameters: `from`, `to`, `work_type`, `page` (25 entries per page). Analytics accepts `from`, `to`, `work_type`; ranges are inclusive and limited to 366 days. Supply both bounds when filtering. Without bounds, entry listing includes all dates; analytics defaults to the current Gregorian year.

Dates in the API are always Gregorian ISO `YYYY-MM-DD`. The frontend converts Jalali dates and year boundaries before sending them. Duration must be `HH:MM` between `00:01` and `24:00`. Time ranges use 24-hour `HH:MM`, must end later the same day, and cannot overlap another timed entry. Split overnight work across dates. Mixed duration and range input is rejected. All entries together may total at most 24 hours per date. Duration-only entries have no start/end and cannot be checked for overlap. Future dates are allowed. Dates and wall-clock times are deliberately timezone-free; the browser defaults the date to local today.

Type matching normalizes case, whitespace, Unicode compatibility and Arabic/Persian variants of kaf/yeh. The first spelling becomes the display name. Suggestions encourage reuse; semantic synonyms and typos are not automatically merged. Types with no remaining entries stay available for reuse.

## Checks and implementation notes

```sh
DJANGO_SECRET_KEY=test-only-key .venv/bin/python manage.py test
```

Nineteen tests cover access isolation, CSRF/session login, API tokens, duration/range validation, Unicode normalization, pagination, updates, caching and analytics. Three concurrency tests run on PostgreSQL (and are skipped on SQLite); they verify daily totals, overlap prevention and preservation of simultaneous partial updates. Per-user row locks serialize creates/updates in PostgreSQL for daily totals and overlap checks. SQLite is for single-process development, not concurrent production writes. Nginx rate-limits both API and admin sign-in across workers, alongside Django's per-worker login throttle. Nginx overwrites incoming forwarding headers; Compose sets TRUSTED_PROXY_COUNT=1 for that internal hop. Direct local Django defaults to zero trusted proxies. Tokens have no automatic expiry; rotate/revoke them using the command above. No shared test users or demo records are created.

Auth implementation follows the [DRF authentication documentation](https://www.django-rest-framework.org/api-guide/authentication/); hosting security guidance follows [Django's checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).


## HTTP integration check

`scripts/http_smoke.py` verifies 25 behaviors through the running frontend proxy, including manifest/icons, security headers, authentication, CSRF, record create/edit/delete, normalization and analytics. Run it **only against a disposable account/database**: it creates and deletes its own test entries, leaving its generated work type available for reuse.

```sh
HOURLEAF_TEST_URL=http://localhost:8081 \
HOURLEAF_TEST_USERNAME=your-test-user \
HOURLEAF_TEST_PASSWORD=your-test-password \
.venv/bin/python scripts/http_smoke.py
```
