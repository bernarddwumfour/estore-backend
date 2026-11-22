# Agent change log

## 2026-11-18 — Service catalog routes and admin navigation
Fixed the service catalog URL patterns in `apps/services/urls.py` so they resolve beneath `/api/services`; the previous missing separator made admin service and category requests return 404. Added route resolution coverage in `apps/services/tests/test_catalog.py`. Added a paginated admin service options endpoint and an admin list page that links each option to its editor on the parent service. Frontend admin navigation now places Appointments immediately below POS and keeps Categories, All Services, and Service Options under Services, while removing the Categories action from the service list. Reduced shared analytics stat card vertical padding and matching loading skeleton spacing. No model or migration changes. Service tests and targeted frontend lint and TypeScript checks pass.

## 2026-11-18 — Service row actions
Added service list actions for viewing, editing, adding and viewing options, featured status, publishing or drafting, restoring archived services, and archiving. Added service option list actions for viewing the parent service, editing, activating or deactivating, setting or unsetting default, and deleting. The option API now returns a conflict when an appointment protects an option from deletion. No model or migration changes.

## 2026-11-18 — Service category actions
Matched Product Categories' row actions in the admin service category table: view details, view full path, edit, activate or deactivate, hide or show, and delete. Service, option, and category tables now show their first three actions before the More menu. No backend model or migration changes.

## 2026-11-18 — Admin service management UI
Added frontend `src/app/dashboard/services/types.ts`, `ServiceForm.tsx`, `page.tsx`, `[id]/page.tsx`, and `categories/page.tsx` for service listing, search and status filtering, drafts and publishing, categories, booking options, and images. Updated frontend `src/app/dashboard/layout.tsx` to group service categories, all services, and appointments together. The screens follow Products' shared DataTable, CustomFilter, CustomPagination, CustomDialog, InfoDialog, ActionsDropdown, and TableSkeleton patterns. Updated backend `apps/services/views/category_views.py` to parse multipart PATCH category image edits; added a regression test in `apps/services/tests/test_catalog.py`. No model or migration changes. Service tests pass on SQLite. Existing unrelated workspace changes were left untouched.

## 2026-11-18 — iPlug service API and request submission
Added `apps/services/management/commands/seed_iplug_services.py` to create four published iPlug services with quote-based, timed options. Added `ServiceRequest` in `apps/services/models.py` and migration `apps/services/migrations/0003_servicerequest.py`; added validation, write service, and public/staff endpoints in `apps/services/schemas/request_schemas.py`, `apps/services/services/request_service.py`, `apps/services/views/request_views.py`, and `apps/services/urls.py`. Added `apps/services/tests/test_requests.py`. The iPlug database was seeded and migrated; the public service list returned all four services. Frontend `src/app/(web)/services/page.tsx` now reads that catalog and submits requests. Frontend `src/app/dashboard/appointments/page.tsx` now shows appointments and service requests on the left in a responsive 2:1 layout. Existing catalog records are preserved by the seed command. Storefront cache revalidation logged connection refusals because the local frontend server was not running; the service data writes succeeded.

## 2026-11-10
Added AI controls to common/models.py and schemas/general_schemas.py; added ai_assistant/features.py; updated all three agents nodes.py and graph.py, ai_assistant/views.py and embeddings/search.py for runtime enforcement. Added products/services/discovery_service.py and wired products/views/product_views.py to semantic fallback. Migration and tests accompany this change. Settings are read from the database so toggles apply across processes. Existing keyword search stays available when AI is disabled.

Validation and supporting files: added common/migrations/0006_generalconfig_ai_admin_enabled_and_more.py and ai_assistant/tests/test_feature_controls.py; updated README.md with feature controls and keyword-first search behavior. Eight focused tests pass. Frontend src/app/dashboard/settings/general/page.tsx adds six switches using the existing settings endpoint, mutation notifications, loading state, and disabled controls. Frontend TypeScript check passes. No changes committed yet.

## 2026-11-10 — Separate storefront semantics from chat
Moved the semantic switch check from ai_assistant/embeddings/search.py to products/services/discovery_service.py. Updated ai_assistant/tests/test_feature_controls.py, README.md, and frontend src/app/dashboard/settings/general/page.tsx to document and verify that shopper/guest semantic retrieval is independent of the storefront toggle. Whole-agent controls remain enforced.

## 2026-11-10 — Label related search results
Updated products/services/discovery_service.py and products/views/product_views.py to return result_type (matching, related, none). Updated ai_assistant/tests/test_feature_controls.py to verify provenance and fallback states. Updated frontend src/widgets/search-modal/SearchModal.tsx to distinguish matching search results from related products and explain the fallback. Scope is the search dialog only.


## 2026-11-22 — Next.js BFF with database-backed browser sessions

Implemented an opaque HttpOnly session cookie and a same-origin Next.js BFF.
Redis configuration is deliberately unchanged. Django stores only session-ID
hashes in the existing database, checks expiry/account status/password fingerprints,
and retains all role/ownership checks. The BFF authenticates itself with a per-store
shared secret. Legacy direct JWT clients remain supported; their existing cache-based
revocation limitations are unchanged. Browser JWT storage and refresh interceptors
were removed. Login, logout, profile restoration, private SSR orders/profile pages,
CSR dashboard, checkout, wishlist, assistant, payment returns, uploads, and inbox
streaming now use sessions. Public product SSR and cache tags are unchanged.

The session cookie is store-specific (localhost cookies are not port-scoped),
HttpOnly and SameSite=Lax, with Secure and the __Host- prefix in production. Mutations
require an exact Origin and custom CSRF header; the BFF does not authorize cross-origin
preflight requests. The proxy fixes its upstream destination, discards browser
credentials, strips JSON credentials, rejects redirects/debug HTML, and preserves
multipart bodies and SSE. Password changes invalidate BFF sessions on the next
request. Login/session failure handling preserves temporary-outage distinctions and
clears private React Query data across logout/account changes. Profile now includes
is_affiliate so restored sessions preserve affiliate navigation.

Validation: 19 focused frontend tests and 12 browser-session backend tests pass.
The full users suite passed 24 tests before the final affiliate regression was added;
that regression passes in the 12-test session suite. Core BFF ESLint and migration
consistency checks pass. The broad frontend suite reported 150 passes and four
unrelated failures in Cart, DataTable, and Slider. Full tsc reports the existing
ProductDetailPageContent extra export in generated oliveandaura route types.
No production migration, secret provisioning, deployment, or Redis operation was
performed. Before rollout apply users.0024_browsersession to each store, configure
matching BFF_SHARED_SECRET values, DJANGO_API_URL and BFF_ORIGIN, and configure a
trusted ingress client-IP header where not on Vercel. See the READMEs and frontend
.env.bff.example. Existing browser sessions must log in again. The user's pre-existing
template editor changes were left untouched.

Files added/changed (grouped by their roles above):
- `estore-backend/.env.example`
- `estore-backend/README.md`
- `estore-backend/apps/users/bff_middleware.py`
- `estore-backend/apps/users/decorators/auth.py`
- `estore-backend/apps/users/management/__init__.py`
- `estore-backend/apps/users/management/commands/__init__.py`
- `estore-backend/apps/users/management/commands/clear_browser_sessions.py`
- `estore-backend/apps/users/migrations/0024_browsersession.py`
- `estore-backend/apps/users/models/__init__.py`
- `estore-backend/apps/users/models/browser_session.py`
- `estore-backend/apps/users/services/browser_session_service.py`
- `estore-backend/apps/users/tests/test_browser_sessions.py`
- `estore-backend/apps/users/views/auth_views.py`
- `estore-backend/apps/users/views/profile_views.py`
- `estore-backend/estore/settings.py`
- `estore-backend/render.yaml`
- `estore-frontend/.env.bff.example`
- `estore-frontend/.gitignore`
- `estore-frontend/README.md`
- `estore-frontend/package-lock.json`
- `estore-frontend/package.json`
- `estore-frontend/src/app/(auth)/change-password/layout.tsx`
- `estore-frontend/src/app/(web)/checkout/page.tsx`
- `estore-frontend/src/app/(web)/order-placed/page.tsx`
- `estore-frontend/src/app/(web)/orders/[id]/page.tsx`
- `estore-frontend/src/app/(web)/orders/callback/page.tsx`
- `estore-frontend/src/app/(web)/orders/page.tsx`
- `estore-frontend/src/app/(web)/orders/success/page.tsx`
- `estore-frontend/src/app/(web)/profile/layout.tsx`
- `estore-frontend/src/app/(web)/wishlist/page.tsx`
- `estore-frontend/src/app/api/bff/[...path]/route.test.ts`
- `estore-frontend/src/app/api/bff/[...path]/route.ts`
- `estore-frontend/src/app/dashboard/DashboardShell.tsx`
- `estore-frontend/src/app/dashboard/layout.tsx`
- `estore-frontend/src/app/dashboard/marketing/social/inbox/page.tsx`
- `estore-frontend/src/app/lib/hooks/use-fetch-wishlist.ts`
- `estore-frontend/src/axios-instances/SecurityAxios.ts`
- `estore-frontend/src/axios-instances/UnAuthenticatedAxios.ts`
- `estore-frontend/src/lib/auth/cookie.ts`
- `estore-frontend/src/lib/providers/auth-provider.test.tsx`
- `estore-frontend/src/lib/providers/auth-provider.tsx`
- `estore-frontend/src/lib/server/backend.ts`
- `estore-frontend/src/lib/server/bff-policy.test.ts`
- `estore-frontend/src/lib/server/bff-policy.ts`
- `estore-frontend/src/middleware.ts`
- `estore-frontend/src/widgets/ai-assistant/AssistantLauncher.tsx`
- `estore-frontend/src/widgets/ai-assistant/ChatAssistant.tsx`


## 2026-11-22 — Configure demo BFF environment credentials

Added a separately generated 64-character BFF_SHARED_SECRET for each demo store,
matching between its frontend and backend. Default .env uses the iPlug secret
because both default processes target the iPlug ports. Frontend DJANGO_API_URL
uses each existing public API URL; BFF_ORIGIN matches localhost ports 3000–3003.
Verified all pairs match and the four stores have distinct secrets without
printing values. Example files retain placeholders. No Redis, database migration,
service restart, or hosted Render/Vercel configuration was changed.

Files changed:
- `estore-frontend/.env.iplug`
- `estore-backend/.env.iplug`
- `estore-frontend/.env`
- `estore-backend/.env`
- `estore-frontend/.env.oakandloom`
- `estore-backend/.env.oakandloom`
- `estore-frontend/.env.tyrepapa`
- `estore-backend/.env.tyrepapa`
- `estore-frontend/.env.oliveandaura`
- `estore-backend/.env.oliveandaura`


## 2026-11-22 — Rewrite both repository READMEs

Replaced starter/append-only documentation in estore-frontend/README.md and
estore-backend/README.md with complete repository guides. Reviewed package scripts,
store registry/runner, Django settings/routes/commands, BFF session flow, workers,
integrations, revalidation handlers, Render configuration, and current test results.
Documented features, architecture, exact store selectors/ports, environment setup,
BFF vs JWT authentication, CSR/private SSR/public caching, integrations, maintenance,
testing, deployment order, known limitations, and troubleshooting. Validated local
Markdown links and code fences. No live credentials are included. This entry is
also a change to estore-backend/models-change-logs.md.

Pre-push review also replaced pre-existing Django/JWT signing-key values in
`estore-backend/.env.example` with explicit placeholders. Real local profiles remain
ignored. Documentation links, code fences, and staged whitespace checks pass.
