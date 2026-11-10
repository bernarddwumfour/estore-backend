# estore-backend
# estore-backend
# estore-backend
# estore-backend
# estore-backend
# Local store environments

Store credentials live in ignored `.env.iplug` and `.env.oakandloom` files.
Run Django management commands through the store selector:

```sh
venv/bin/python manage_store.py iplug runserver
venv/bin/python manage_store.py oak runserver
```

The same selector works with other management commands, for example
`venv/bin/python manage_store.py oak migrate` or `createsuperuser`. Run one
API on port 8000 at a time, or provide a different port to `runserver` and
set the matching frontend API URL. Oak & Loom's payment and social credentials
must be configured separately before enabling those integrations.

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
