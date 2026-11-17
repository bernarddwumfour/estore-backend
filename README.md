# estore-backend
# estore-backend
# estore-backend
# estore-backend
# estore-backend
# Local store environments

Store credentials live in ignored `.env.iplug`, `.env.oakandloom`,
`.env.tyrepapa`, and `.env.oliveandaura` files.
Run Django management commands through the store selector:

```sh
venv/bin/python manage_store.py iplug runserver
venv/bin/python manage_store.py oak runserver
venv/bin/python manage_store.py tyrepapa runserver
venv/bin/python manage_store.py oliveandaura runserver
```

The selector chooses ports 8000 (iPlug), 8001 (Oak & Loom), 8002 (TyrePapa),
and 8003 (Olive & Aura). These pair with frontend ports 3000, 3001, 3002, and
3003 respectively. Pass an explicit `runserver` address to override a default.

Olive & Aura has its own database profile. Set `DATABASE_URL` in
`.env.oliveandaura` to the dedicated beauty database before running database or
server commands. Until then, the store selector blocks those commands to avoid
falling back to the shared local SQLite database. Once configured, run
`venv/bin/python manage_store.py oliveandaura migrate` to prepare that database.

The same selector works with other management commands, for example
`venv/bin/python manage_store.py oak migrate` or `createsuperuser`. Oak & Loom's
payment and social credentials must be configured separately before enabling
those integrations.

### Social shopping agent

Set `ZERNIO_WEBHOOK_SECRET` to the secret configured on the Zernio webhook and
`STOREFRONT_BASE_URL` to the public storefront origin. Apply the social
migrations and configure Zernio to send `message.received` events to the public
`/api/social/webhooks/zernio` endpoint.

Without Redis, run the database-backed worker in a separate process:

```sh
venv/bin/python manage_store.py iplug migrate social
venv/bin/python manage_store.py iplug run_social_agent_worker
```

With `REDIS_URL` configured, run a Celery worker and Celery beat with the
store's `ESTORE_ENV_FILE` instead. Enable replies for each connected account in
the social inbox. The global AI and guest-agent controls must also be enabled.
Interrupted sends are flagged for staff review rather than retried blindly.

The staff inbox uses an authenticated server-sent event stream for refresh
notifications. Each stream lasts up to 45 seconds and checks a shared database
revision every two seconds; the browser reconnects and falls back to slower
polling if streaming is unavailable. WSGI deployments must use threaded or
otherwise concurrent workers, allow long-lived streaming responses, and disable
proxy buffering for this endpoint. The Render start command uses threaded
Gunicorn workers. At larger scale, replace the per-stream database checks with a
shared publish/subscribe service.

## Product search embeddings

Saving a product or saving/deleting a variant schedules a refresh after the
database transaction commits. The worker also reconciles published products
hourly, including changes made through bulk updates. Only changed searchable
content is sent to the embedding provider. Set `OPENAI_API_KEY` for the worker
and use the same embedding model settings as the API.

With Redis configured, run one Celery worker with Beat enabled for each store:

```sh
venv/bin/python manage_store.py oak shell -c 'from estore.celery import app; app.worker_main(["worker", "-B", "-l", "info"])'
```

The Render worker is configured with Beat; run only one Beat scheduler per
store even if additional workers are deployed. Without Redis, refreshes run
inline after catalog changes; hourly reconciliation requires Redis and a
running Celery worker with Beat.

## AI controls and product discovery

Dashboard → Settings → General contains store-specific switches for all AI,
storefront semantic product search, chat product discovery, and shopper/guest/admin agents.
All switches default to enabled. Changes are enforced by the API and at agent
model/tool execution, including cached graphs; no server restart is needed for
setting changes. Disabled agents cannot confirm previously prepared actions.

Public `/api/products/search?q=...` first uses keyword search. If no keyword
matches exist, it searches product embeddings and returns verified published
catalog products in relevance order. Disabling semantic search or all AI keeps
keyword search available. Provider failures fall back to the keyword response.
The semantic candidate pool is capped at 200 products. Each store needs its own
populated embedding index and the common app migrations applied.

The storefront semantic-search switch does not affect shopper or guest semantic
search. Use their agent switches to disable those assistants entirely.
