# Agent change log

## 2026-11-10
Added AI controls to common/models.py and schemas/general_schemas.py; added ai_assistant/features.py; updated all three agents nodes.py and graph.py, ai_assistant/views.py and embeddings/search.py for runtime enforcement. Added products/services/discovery_service.py and wired products/views/product_views.py to semantic fallback. Migration and tests accompany this change. Settings are read from the database so toggles apply across processes. Existing keyword search stays available when AI is disabled.

Validation and supporting files: added common/migrations/0006_generalconfig_ai_admin_enabled_and_more.py and ai_assistant/tests/test_feature_controls.py; updated README.md with feature controls and keyword-first search behavior. Eight focused tests pass. Frontend src/app/dashboard/settings/general/page.tsx adds six switches using the existing settings endpoint, mutation notifications, loading state, and disabled controls. Frontend TypeScript check passes. No changes committed yet.

## 2026-11-10 — Separate storefront semantics from chat
Moved the semantic switch check from ai_assistant/embeddings/search.py to products/services/discovery_service.py. Updated ai_assistant/tests/test_feature_controls.py, README.md, and frontend src/app/dashboard/settings/general/page.tsx to document and verify that shopper/guest semantic retrieval is independent of the storefront toggle. Whole-agent controls remain enforced.

## 2026-11-10 — Label related search results
Updated products/services/discovery_service.py and products/views/product_views.py to return result_type (matching, related, none). Updated ai_assistant/tests/test_feature_controls.py to verify provenance and fallback states. Updated frontend src/widgets/search-modal/SearchModal.tsx to distinguish matching search results from related products and explain the fallback. Scope is the search dialog only.
