# Backend Engineering Rules — estore-backend

Authoritative conventions for this Django project. Derived from the existing
codebase plus the standards we benchmarked against (OWASP API Security Top 10
2023, OWASP ASVS, PCI DSS 4.0.1, RFC 8725 JWT BCP, OWASP Django Cheat Sheet,
12-Factor App, Stripe webhook SOP, NIST SP 800-204). New code MUST follow these.
When a rule and an existing file disagree, the rule wins — fix the file.

---

## 1. Architecture & layering

- **No DRF.** Plain Django function-based views returning the shared response
  envelope. Do not introduce serializers/viewsets/routers.
- Every app is layered. Keep the boundaries strict:
  - `views/` — HTTP only: parse, authorize, validate, call a service/selector,
    serialize, return. **No ORM writes and no business rules in views.**
  - `schemas/` (or `schemas.py`) — request validation → `(cleaned, errors)`
    tuples, and serialization helpers. Pure functions, no DB writes.
  - `selectors/` (or `selectors.py`) — **read** queries only. Never mutate.
  - `services/` (or `services.py`) — **write**/business logic. All mutations
    live here.
- A view calls services and selectors; services may call selectors; **selectors
  never call services**, and nothing imports back into views.
- Cross-app access goes through the other app's selectors/services, never by
  reaching into its ORM directly from a view.
- Prefer the package form (`views/`, `services/`, …) for any app that grows
  past a single screen of code, matching `apps/products`.

## 2. Response envelope

- Always return via the shared helper — never a bare `JsonResponse`/`dict`.
  The products/orders apps use `common.responses` (`ok`, `created`,
  `bad_request`, …); promotions uses `estore.utils.responses.APIResponse`.
  **Pick the one already imported in the app you're editing and stay
  consistent within that app.** (Consolidating to one module is a tracked
  cleanup — see §12.)
- Every response is `{ "data": ..., "message": ..., "errors": ... }`.
- Status codes are meaningful: 200 ok, 201 created, 400 validation/bad input,
  401 unauthenticated, 403 wrong role, 404 missing, 409 conflict, 500 unexpected.
- **Validation failures are 400, never 500.** If malformed user input can reach
  a `500`, that is a bug (see the `Decimal`/`InvalidOperation` class of bugs).

## 3. Validation

- All external input passes through a `validate_*` function returning
  `(cleaned, errors)`. Views act on `errors` before touching a service.
- Validators must be **total**: any input type (None, "", wrong type, garbage
  string) yields an `errors` dict, never an exception. When parsing:
  - `Decimal(...)` → catch `(TypeError, ValueError, InvalidOperation)`.
  - `int(...)`/`float(...)` → catch `(TypeError, ValueError)`.
  - UUID lookups in selectors → catch `(Model.DoesNotExist, ValueError,
    ValidationError)` so a malformed UUID is a clean miss, not a 500.
- Validate cross-field invariants (e.g. `ends_at > starts_at`,
  `quantity >= 1`).
- Truncate/limit string lengths to the model's `max_length` in the validator.

## 4. Security

- **No secrets in code.** Everything via `config(...)`/`os.getenv(...)` from
  `.env` (gitignored). `.env.example` documents every key with a placeholder.
  Never re-hardcode a credential, even temporarily.
- `SECRET_KEY` has **no fallback default**. `DEBUG` defaults to `False`.
- Auth: `@jwt_required`, then `@role_required(...)` for admin/staff routes.
  Public endpoints are the explicit exception and should say so in the docstring.
- Enforce **object-level ownership** (BOLA/IDOR): a user may only read/mutate
  their own resources; admin/staff bypass is explicit. Never trust an ID in the
  path to imply ownership.
- JWT: HS256, short-lived access (15 min) + refresh (7 days), with `iss`/`aud`
  claims and `jti`. Decode with `require=["exp","iat","jti","aud","iss"]` and
  check the revocation deny-list. Rotate refresh tokens on use; revoke on logout.
- Rate-limit every endpoint with `@ratelimit` (`key='ip'` for public,
  `key='user'` for authed). Login also rate-limits per-email.
- Webhooks: verify the signature with `hmac.compare_digest`, make handlers
  **idempotent**, and return `200` fast even on internal error (log it; never
  leak `str(e)` to the caller).
- **Never leak internals** in responses: no `str(e)`, stack traces, SQL, or
  provider error bodies. Log the detail server-side; return a generic message.

## 5. Data integrity & transactions

- Wrap multi-write operations in `@transaction.atomic` (or a `with` block).
- **Stock / counters that can race** must use an atomic conditional update, not
  read-modify-write:
  ```python
  updated = Variant.objects.filter(pk=pk, stock__gte=qty).update(stock=F("stock") - qty)
  if not updated:
      raise ValueError("insufficient stock")
  ```
  Use the model's `reduce_stock()`/`increase_stock()` helpers; do not re-roll
  `obj.stock -= n; obj.save()`. When locking rows instead, use
  `select_for_update()` inside the atomic block.
- Snapshot prices/costs at write time (e.g. `original_price`,
  `cost_price_snapshot`) so later catalog edits don't rewrite history.
- Money is `Decimal` end-to-end; only convert to `float` at serialization.
- Use `unique`/`unique_together` constraints and DB indexes for the access
  patterns you actually query (status+date ranges, slugs, FKs).

## 6. Audit logging (hard-won rule)

- Use `apps.common.logging.log_action(...)` for auditable actions. It persists
  to `SystemLog`.
- **Audit logging must NEVER affect the caller's transaction.** The DB write is
  confined to a `transaction.atomic()` savepoint and `extra` is sanitised with
  `json.loads(json.dumps(extra, default=str))`. Do not "optimise" this away.
- Consequence rule: **never put a raw non-JSON value (UUID, Decimal, datetime,
  model instance) directly into `extra`** and never let a logging call sit
  un-savepointed inside a business `atomic` block. A serialization failure there
  silently rolled back a successful write while the API returned `201`.
- `status_code=0` means "request start" and is not persisted; `DEBUG` severity
  is not persisted.

## 7. Error handling

- Services return `(result, error)` / `(success, error_dict)` tuples; they do
  not raise across the view boundary for expected failures.
- Catch specific exceptions (`Model.DoesNotExist`, `ValueError`,
  `IntegrityError`, …). A bare `except Exception` is allowed only as the final
  safety net that logs and returns `server_error()`.
- Reads that miss return `None` (selector) and the view maps that to 404.

## 8. Tests (required for every app)

- Tests live in a `tests/` **package** (not `tests.py`), with a shared
  `factories.py` of plain builder helpers. Mirror `apps/products/tests/`.
- Cover, at minimum: model properties/methods, every validator (happy path +
  each failure branch), services (success, each guard/rollback path), and
  selectors (filters, visibility rules, pagination, malformed input).
- Add a regression test for every bug fixed, asserting the **DB end state**,
  not just the status code.
- Run locally on sqlite:
  ```bash
  SECRET_KEY=test-secret DEBUG=True DB_SSL_REQUIRE=False \
    DATABASE_URL="sqlite:///test.sqlite3" REDIS_URL="" \
    python manage.py test apps.<app>
  ```

## 9. Migrations

- Every model change ships with its migration in the same commit. Never edit a
  model without `makemigrations`.
- No data loss in migrations without an explicit, reviewed data migration.

## 10. URLs & naming

- Routes are registered under `/api/<app>` via each app's `urls.py` with an
  `app_name` and named patterns.
- Admin routes are namespaced `/admin/...`; declare more specific paths before
  greedy `<slug>` catch-alls (slug routes shadow siblings otherwise).
- View names: `noun_verb` / `admin_noun_verb`; service methods are verbs on a
  `XService` class.

## 11. Python style

- Type-hint public functions. Module-level `logger = logging.getLogger(__name__)`.
- Keep imports at module top; the lazy-import exception is only to break genuine
  circular imports (and `apps.common.models` inside the logger).
- Match surrounding code's naming, docstring style, and comment density.

## 12. Known cleanups (don't add to these)

- Two response modules exist (`common.responses` and
  `estore.utils.responses`); consolidate to one over time. Until then, match the
  app you're in.
- Heavy per-method `log_action` boilerplate should migrate to a
  decorator/middleware. Don't copy-paste more of it than necessary.
- Synchronous audit logging should move to a background worker once a broker
  (Redis/Celery) is provisioned.

## 13. Before "done"

- [ ] No secret added to tracked files; `.env.example` updated if a key was added.
- [ ] Input validated; malformed input returns 400, not 500.
- [ ] Auth + role + ownership enforced; rate limit present.
- [ ] Writes atomic; races handled with `F()`/`select_for_update()`.
- [ ] No internal detail leaked in responses.
- [ ] Tests added/updated and passing on sqlite; regression test for any bug.
- [ ] Migration created if models changed.
