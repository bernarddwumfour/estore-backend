# eStore Backend

Django API and background services for **iPlug**, **Oak & Loom**, **TyrePapa**, and **Olive & Aura**. The same codebase runs against separately configured store environments and databases.

Companion repository: [eStore Frontend](https://github.com/bernarddwumfour/estore-frontend).

## Contents

- [Capabilities](#capabilities)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Local setup and store profiles](#local-setup-and-store-profiles)
- [Configuration](#configuration)
- [Authentication and authorization](#authentication-and-authorization)
- [API organization](#api-organization)
- [Integrations](#integrations)
- [Workers and scheduled tasks](#workers-and-scheduled-tasks)
- [AI and product discovery](#ai-and-product-discovery)
- [Management commands](#management-commands)
- [Tests and engineering conventions](#tests-and-engineering-conventions)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)

## Capabilities

| App | Responsibilities |
| --- | --- |
| `users` | Customer/staff accounts, profiles, addresses, verification, password recovery, affiliates, browser sessions, and user analytics. |
| `products` | Catalog, categories, variants, images, inventory, wishlists, reviews, search, and analytics. |
| `orders` | Checkout, orders, payment verification/webhooks, transactions, shipping, and order operations. |
| `services` | Service catalog, categories, options, appointments, and service requests. |
| `promotions` / `marketing` | Promotions, discount codes, campaign operations, and marketing statistics. |
| `blog` | Blog posts and categories, publication, and storefront invalidation. |
| `social` | Social accounts, publishing, comments, inbox conversations, webhook processing, and agent handoff. |
| `templates` | Reusable design templates, groups, categories, previews, assets, and saved instances. |
| `ai_assistant` | Shopper, guest, and admin assistants; action preparation/confirmation; product embeddings. |
| `common` | General configuration, AI switches, audit logs, and shared utilities. |

## Architecture

The backend uses **Django 4.2.11**, plain Django views (not Django REST Framework), PostgreSQL or SQLite, PyJWT, Celery, Redis-compatible caching, Cloudinary, Resend, and OpenAI/LangGraph integrations. Exact dependencies are pinned in [requirements.txt](requirements.txt).

```text
Browser → Next.js BFF → Django views → services/selectors → store database
                         │
                         ├─ payment, shipping, email, media, social providers
                         └─ queued or inline background work
```

Views handle HTTP and authorization. Schemas validate inputs; selectors read data; services contain business logic and writes. Role and resource-ownership checks remain in Django even when Next.js validates a session first.

Store profiles select configuration and databases at process startup. This is not a single runtime that chooses a tenant database from each incoming request. Run separate API/worker processes for separate store environments.

## Requirements

- Python and a virtual environment compatible with [requirements.txt](requirements.txt). The repository's tooling targets Python 3.11 in [pyproject.toml](pyproject.toml).
- PostgreSQL for a hosted store, or SQLite for local tests and basic development.
- A corresponding Next.js frontend for browser flows.
- Provider credentials only for the integrations you intend to exercise.
- Redis-compatible storage and a Celery worker when asynchronous broker-backed work is enabled. BFF browser sessions themselves use the database.

## Local setup and store profiles

```bash
git clone https://github.com/bernarddwumfour/estore-backend.git
cd estore-backend
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env.iplug
```

Review the copied values and configure a database, Django secret, matching BFF secret, and local origins before running commands. Minimal local values look like:

```dotenv
SECRET_KEY=replace-with-a-random-django-secret
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///iplug.sqlite3
DB_SSL_REQUIRE=False
FRONTEND_BASE_URL=http://localhost:3000
STOREFRONT_BASE_URL=http://localhost:3000
BFF_SHARED_SECRET=replace-with-the-matching-nextjs-secret
REVALIDATE_SECRET=replace-with-the-matching-revalidation-secret
REDIS_URL=
```

Generate distinct Django, BFF, and revalidation secrets. Copy each BFF/revalidation value to its corresponding frontend setting; do not independently generate two different values for one shared credential.

```bash
venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))"
venv/bin/python manage_store.py iplug migrate
venv/bin/python manage_store.py iplug createsuperuser
venv/bin/python manage_store.py iplug runserver
```

The project's `createsuperuser` command uses its admin-user creation path. Other dashboard accounts need the `staff` or `admin` application role; `/admin/` is Django's separate administration interface.

| Store selector | Environment file | API port | Frontend port |
| --- | --- | --- | --- |
| `iplug` | `.env.iplug` | 8000 | 3000 |
| `oak` or `oakandloom` | `.env.oakandloom` | 8001 | 3001 |
| `tyrepapa` | `.env.tyrepapa` | 8002 | 3002 |
| `oliveandaura` | `.env.oliveandaura` | 8003 | 3003 |
| `velora` | `.env.velora` | 8004 | 3004 |

```bash
venv/bin/python manage_store.py oak runserver
venv/bin/python manage_store.py tyrepapa runserver
venv/bin/python manage_store.py oliveandaura runserver
venv/bin/python manage_store.py velora runserver
```

Create each profile with its own database and matching frontend origins. The local Velora profile currently copies iPlug's database and provider settings for previewing; its API port and frontend origins are separate. An explicit `runserver` address overrides the default port. The selector also supports commands such as `migrate`, `shell`, and `createsuperuser`. Standard `manage.py` uses the normal environment/default `.env`; `ESTORE_ENV_FILE` explicitly chooses a profile.

Olive & Aura's selector refuses database/server commands until its profile contains a `DATABASE_URL`, preventing an accidental fallback to the default database. Profiles contain local credentials and are ignored by Git. Their presence in a developer workspace does not configure Render.

## Configuration

Use [.env.example](.env.example) as a starting point and [estore/settings.py](estore/settings.py) as the authoritative list of settings and defaults.

### Core settings

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Required Django secret; no fallback value. |
| `DEBUG` | Defaults to `False`; use `True` only for local development. |
| `ALLOWED_HOSTS` | Comma-separated API hostnames. |
| `DATABASE_URL` | Database connection string. Without it, the default is local `db.sqlite3`. |
| `DB_SSL_REQUIRE` | Database TLS setting; disable for SQLite/local connections that do not support it. |
| `ESTORE_ENV_FILE` | Store environment file, normally selected by `manage_store.py`. |
| `FRONTEND_BASE_URL` | Frontend origin used by application flows and the configured CORS allowlist. |
| `STOREFRONT_BASE_URL` | Storefront origin used for public links and revalidation callbacks. |
| `BFF_SHARED_SECRET` | Shared server credential matching the store's Next.js BFF. Empty disables BFF authentication. |
| `REVALIDATE_SECRET` | Separate shared credential for Next.js cache invalidation callbacks. |
| `REDIS_URL` | Shared cache and Celery broker/result connection; leaving it empty enables local fallback behavior. |
| `JWT_SECRET_KEY`, `JWT_ISSUER`, `JWT_AUDIENCE` | Legacy JWT signing and claim validation. Signing key defaults to Django's secret if omitted. |

CORS and trusted CSRF origins are configured in `settings.py`; the current code does **not** read a general `CSRF_TRUSTED_ORIGINS` environment variable. Review those settings when introducing new deployed origins. Next.js BFF mutation protection has its own `BFF_ORIGIN` setting on the frontend server.

### Provider and store settings

| Integration | Main variables |
| --- | --- |
| Paystack | `PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY`, `PAYSTACK_WEBHOOK_SECRET`, `PAYSTACK_CALLBACK_URL`, `PAYMENT_SUCCESS_URL`, `PAYMENT_CANCEL_URL` |
| Terminal Africa | `TERMINAL_AFRICA_API_KEY`, `TERMINAL_AFRICA_BASE_URL`, `TERMINAL_AFRICA_WEBHOOK_SECRET` |
| Cloudinary | `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` |
| Resend/email | `RESEND_API_KEY`, `SENDER_EMAIL`, `DEFAULT_FROM_NAME`, `SITE_NAME`, `DISABLE_EMAIL_VERIFICATION` |
| Social/Zernio | `ZERNIO_API_KEY`, `ZERNIO_WEBHOOK_SECRET`, `ZERNIO_BASE_URL`, optional `ZERNIO_PLATFORMS` |
| AI/search | `OPENAI_API_KEY`, `AI_EMBEDDING_MODEL`, `AI_EMBEDDING_DIMENSIONS`, `AI_EMBEDDING_CACHE_TTL`, `AI_SEMANTIC_MIN_SIMILARITY`, `AI_SEMANTIC_SCORE_MARGIN` |
| Link construction | `DOMAIN_NAME`, `USE_HTTPS`, frontend/storefront URLs |
| Pickup/affiliate defaults | `STORE_ADDRESS_*`, `AFFILIATE_CODE_DISCOUNT_TYPE`, `AFFILIATE_CODE_DISCOUNT_VALUE`, `AFFILIATE_COMMISSION_BASE` |

Configure credentials per store. Unconfigured providers do not become available merely because their dashboard pages exist.

## Authentication and authorization

### Browser sessions through Next.js

The browser holds an opaque session ID in a Next.js `HttpOnly` cookie. Next.js sends it as `X-BFF-Session`, alongside `X-BFF-Key` containing the shared server credential.

[BFFMiddleware](apps/users/bff_middleware.py) verifies the server credential before trusting the session header. [BrowserSession](apps/users/models/browser_session.py) stores the session ID's SHA-256 digest, user, password fingerprint, creation time, and expiry. Plaintext session IDs and refresh-token pairs are not stored in that table.

- Sessions last seven days.
- Logout deletes the session record.
- Expiry, account deactivation, and a changed password fingerprint reject subsequent requests.
- Roles are read from the current database user, not trusted from browser claims.
- Existing role and ownership decorators protect business endpoints.
- Cache loss cannot restore a deleted database-backed browser session.

Apply migration `users.0024_browsersession` before deploying the BFF frontend. Schedule `clear_browser_sessions` to remove expired rows. A trusted BFF can optionally supply `X-BFF-Client-IP`; public callers cannot use that header to bypass the server credential check.

### Direct JWT clients

Existing API clients can still use `Authorization: Bearer <access-token>`. Access tokens last 15 minutes and refresh tokens seven days. Validation checks the configured algorithm, issuer, audience, required claims, token type, and revocation cache. Refresh rotation and logout revocation remain available through the existing endpoints.

This legacy flow is separate from BFF sessions. Its revocation records still depend on the configured cache; local process memory is not durable or shared. Password-fingerprint invalidation described above applies to BFF sessions, not retroactively to every legacy JWT. Clearing the old browser cookie does not revoke a copied JWT held elsewhere.

## API organization

All application APIs are mounted beneath `/api`:

| Prefix | Routes |
| --- | --- |
| `/api/users` | Login, staff login, profile, recovery, guests, affiliates, and administration. |
| `/api/products` | Public catalog/search/reviews and protected catalog management. |
| `/api/orders` | Checkout, orders, payments, shipping, and administration. |
| `/api/services` | Services, options, requests, and appointments. |
| `/api/promotions` | Public and protected promotion operations. |
| `/api/marketing` | Discounts, campaigns, and marketing operations. |
| `/api/blog` | Posts and categories. |
| `/api/social` | Provider webhooks, account management, posts, and inbox. |
| `/api/templates` | Staff design-template operations. |
| `/api/common` | Store configuration and logs. |
| `/api/assistant/` | Guest, shopper, admin, and action-confirmation endpoints. |

See each app's `urls.py` for exact routes and methods. Most app routes omit a trailing slash; assistant routes require one. Next.js normalizes this distinction for browser requests.

Responses use `APIResponse`:

```json
{
  "success": true,
  "message": "Success",
  "data": { "id": "..." }
}
```

Empty `data`/`errors` fields may be omitted. HTTP status codes identify authentication, permission, validation, missing-resource, and server failures; some existing validation responses use 422. Upload endpoints accept multipart data where declared by their views.

## Integrations

### Payments and shipping

Paystack supports order payment initialization, callback verification, and the `/api/orders/paystack-webhook` endpoint. Configure public callback URLs for the correct store. Payment-reference lookup uses the cache in parts of the flow, so multi-process deployments require a shared cache.

Terminal Africa supplies shipping operations; its API credentials and webhook settings are independent of Paystack. Store pickup details and shipping defaults are configured through the existing settings and dashboard configuration.

### Media and email

Cloudinary stores uploaded media when its credentials are configured. Development can serve local media when `DEBUG=True`; production requires appropriate media/static hosting. Resend handles transactional email and verification flows. Configure an appropriate sender and the correct link origins before testing registration or password recovery.

### Social inbox and automation

Configure Zernio to send `message.received` and `comment.received` events to `/api/social/webhooks/zernio`, using the configured webhook secret. Account-level message/comment reply switches and applicable global AI controls determine whether agents respond. Unverified comment authors and uncertain/interrupted sends are flagged for review rather than blindly retried.

The staff inbox exposes authenticated SSE notifications. Streams last up to 45 seconds and inspect a shared database revision every two seconds. Browsers reconnect and retain polling fallback. WSGI/proxy deployments need concurrent workers and streaming without buffering.

### Storefront cache invalidation

Relevant catalog, category, blog, and service writes trigger fixed Next.js revalidation callbacks after database commit. Configure `STOREFRONT_BASE_URL` and matching `REVALIDATE_SECRET` on both applications. Callbacks authenticate with a bearer secret and do not accept arbitrary cache paths/tags. A frontend acceptance indicator reports callback acceptance, not an end-user browser check.

## Workers and scheduled tasks

With no `REDIS_URL`, Django uses process-local cache and Celery tasks run eagerly/inline. This is useful for development but does not provide shared revocation/rate-limit/payment-reference state across workers.

For durable social event processing without a Redis broker, run a separate process:

```bash
venv/bin/python manage_store.py iplug run_social_agent_worker
```

With Redis configured, tasks are queued and need a running worker. Start a store-specific worker and Beat scheduler through the profile loader:

```bash
venv/bin/python manage_store.py oak shell -c 'from estore.celery import app; app.worker_main(["worker", "-B", "-l", "info"])'
```

Run only **one Beat scheduler per store**. The configured schedule recovers pending social messages every minute and reconciles product embeddings hourly. Separate stores need isolated queues/cache namespaces or separate Redis instances; the current default settings do not automatically namespace all shared state by store.

Adding `REDIS_URL` changes task execution from inline to queued. Do not enable it without arranging the corresponding worker. The BFF session table does not require Redis, but other existing application features still use the cache. The Render Blueprint currently declares a free Redis-compatible service; assess persistence and eviction requirements before treating it as durable production state.

## AI and product discovery

The dashboard's general settings contain switches for all AI, storefront semantic search, chat product discovery, and shopper/guest/admin agents. API and agent execution enforce these settings without requiring a restart. Disabled agents cannot confirm previously prepared actions.

Public `/api/products/search?q=...` tries keyword matching first. If no keyword matches exist and semantic search is enabled, it searches embeddings and returns published catalog candidates. Provider failures or disabled semantic search leave keyword search available. The semantic candidate pool is capped at 200 products.

Product/variant changes schedule indexing after commit; reconciliation catches other changes. Only changed searchable content is sent for embedding. Configure the same embedding model and dimensions on API and worker processes, and populate an index for each store:

```bash
venv/bin/python manage_store.py iplug index_product_embeddings
```

`--force` clears existing embedding records and rebuilds them; use it deliberately. Without a broker-backed scheduler, the hourly reconciliation does not run automatically. The storefront semantic-search switch is independent of shopper/guest chat search switches.

AI-backed actions use the implemented preparation/confirmation flows. No provider key is required to run basic non-AI catalog operations. Features that need the model or embedding service require valid configuration and populated data.

## Management commands

Run commands through `manage_store.py <store>` to avoid targeting the wrong database. Inspect `help <command>` before invoking data-changing seed/import commands.

| Command | Purpose |
| --- | --- |
| `migrate` | Apply the store's schema migrations. |
| `createsuperuser` | Create a Django administration account. |
| `clear_browser_sessions` | Delete expired BFF sessions; suitable for daily scheduling. |
| `cleanup_logs` | Remove logs according to command options. |
| `cancel_unpaid_orders` | Process unpaid orders according to command rules/options. |
| `run_social_agent_worker` | Process durable social events without a Redis broker; supports `--once` and `--interval`. |
| `index_product_embeddings` | Index published products; optional destructive rebuild with `--force`. |
| `seed_iplug_services` | Populate the iPlug service examples. |
| `seed_oliveandaura_services` | Populate Olive & Aura service examples. |
| `seed_oliveandaura_products` | Populate Olive & Aura product examples. |
| `attach_oliveandaura_images` | Attach beauty product imagery according to command inputs. |
| `seed_tyrepapa_blogs` | Populate TyrePapa blog examples. |

Do not run every seed against every store. Seeds and attachments can write records or invoke external providers; they are optional, not prerequisites for migrations or tests.

## Tests and engineering conventions

Tests live in app-specific `tests/` packages and use fixture factories. To run user/session tests against SQLite without a broker:

```bash
SECRET_KEY=test-secret DEBUG=True DB_SSL_REQUIRE=False \
DATABASE_URL="sqlite:///test.sqlite3" REDIS_URL="" \
venv/bin/python manage.py test apps.users --noinput
```

Use `apps.users.tests.test_browser_sessions` for focused BFF coverage, or select another app package. Run migration consistency checks after model changes:

```bash
SECRET_KEY=test-secret DEBUG=True DB_SSL_REQUIRE=False \
DATABASE_URL="sqlite:///test.sqlite3" REDIS_URL="" \
venv/bin/python manage.py makemigrations --check --dry-run
```

Use an isolated environment, not a store profile pointing at a hosted database, for tests. Ruff configuration is in [pyproject.toml](pyproject.toml); Ruff is separate development tooling, not a pinned runtime dependency.

[RULES.md](RULES.md) defines layering, validation, transactional writes, authorization, audit logging, tests, and migration conventions. Agent-driven changes are recorded in [models-change-logs.md](models-change-logs.md).

**Recorded verification, 2026-11-22:** the users suite passed 24 tests before the final affiliate-session regression was added; all 12 focused session tests, including that regression, passed afterward. Migration consistency checks passed. This is not a claim that every app/provider integration has been exercised against a deployed environment.

## Deployment

[render.yaml](render.yaml) defines an API service, Celery worker with Beat, database, and Redis-compatible service. [build.sh](build.sh) installs requirements, collects static files, and applies migrations. Both service definitions currently use that build script; account for migration execution when coordinating deployments.

The API command uses threaded Gunicorn workers and a 75-second timeout to accommodate inbox streams. The Blueprint is a starting point for one store environment, not automatic provisioning of all four demo stores.

1. Configure the store database, Django secret, allowed hosts, and provider credentials in the hosting environment.
2. Use `DEBUG=False`, the intended database TLS setting, and appropriate public frontend/storefront URLs.
3. Set `BFF_SHARED_SECRET` to match Next.js, and set the separate revalidation secret on both servers.
4. Apply migrations before enabling the new frontend, including `users.0024_browsersession`.
5. Give API and worker processes matching database, application/signing secrets, AI/provider settings, and broker configuration where required.
6. Start one Beat scheduler per store and schedule expired browser-session cleanup.
7. Verify login, profile, logout, permissions, checkout/payment verification, uploads, and social streaming end to end.

The Blueprint does not enumerate every provider variable or deployment-specific origin. Set omitted values explicitly. Local env files are ignored and do not configure hosted services when you push. Existing browser users must sign in again after the BFF migration. Legacy JWT clients remain supported.

Production settings enable HTTPS redirects, secure Django cookies, HSTS, and forwarded-protocol handling. Configure trusted origins in `settings.py` for the actual deployment. Verify static/media delivery and reverse-proxy streaming behavior independently of application startup.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Browser session rejected with 403 | Matching, nonempty BFF shared secrets and Next.js origin/CSRF checks. |
| Browser session rejected with 401 | Expiry, deletion, password change, deactivated user, or missing session cookie. |
| Browser-session table is missing | Run migrations against the correct store database. |
| Olive & Aura command refuses to run | Set its dedicated `DATABASE_URL` in `.env.oliveandaura`. |
| SQLite reports an SSL option error | Use `DB_SSL_REQUIRE=False`. |
| Tasks stop running after adding Redis | Start the store's Celery worker; tasks are now queued. |
| Different workers disagree about limits/revocation | Process-local cache is not shared; review the existing Redis configuration. |
| Product search has no semantic results | API key, model/dimensions, AI switches, published catalog, and populated embedding index. |
| Social replies stay pending | Database worker or Celery worker/Beat, webhook secret, account switches, and handoff state. |
| Inbox repeatedly disconnects | Worker concurrency, 45-second stream duration, proxy buffering, and frontend-host limits. |
| Email links point at the wrong store | Frontend/domain/protocol settings and the selected profile. |
| Updates do not appear on the storefront | Revalidation secret, storefront URL, callback reachability, and frontend cache behavior. |
| Direct browser CORS or Django CSRF rejection | Review actual settings; adding an unused environment variable will not change hard-coded origin lists. |
