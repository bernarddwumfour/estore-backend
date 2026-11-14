from types import SimpleNamespace
from unittest.mock import patch
from django.test import SimpleTestCase
from apps.ai_assistant.features import enabled, available_tools, require_agent
from apps.common.schemas.general_schemas import validate_general_config_update
from apps.products.services.discovery_service import search_catalog

class FeatureControlTests(SimpleTestCase):
    def setUp(self):
        patcher = patch("apps.products.services.discovery_service.enabled", return_value=True)
        self.storefront_flag = patcher.start()
        self.addCleanup(patcher.stop)

    @patch('apps.ai_assistant.features.GeneralConfig.get')
    def test_master_override_and_agent_switch(self, get):
        get.return_value = SimpleNamespace(ai_enabled=False, ai_shopper_enabled=True)
        self.assertFalse(enabled('shopper'))
        get.return_value.ai_enabled=True
        self.assertTrue(enabled('shopper'))
        get.return_value.ai_shopper_enabled=False
        self.assertFalse(enabled('shopper'))

    @patch('apps.ai_assistant.features.GeneralConfig.get')
    def test_disabled_discovery_removed_from_tool_execution(self, get):
        get.return_value=SimpleNamespace(ai_enabled=True, ai_shopper_enabled=True, ai_discovery_enabled=False)
        tools=[SimpleNamespace(name='search_products'),SimpleNamespace(name='prepare_order')]
        self.assertEqual(available_tools(tools,'shopper'),tools[1:])

    @patch('apps.ai_assistant.features.enabled', return_value=False)
    def test_disabled_agent_blocks_endpoint(self, flag):
        @require_agent('shopper')
        def endpoint():
            self.fail('Disabled endpoint must not execute')
        self.assertEqual(endpoint().status_code,403)

    def test_flags_require_booleans(self):
        cleaned,errors=validate_general_config_update({'ai_enabled':'false'})
        self.assertIn('ai_enabled',errors)
        cleaned,errors=validate_general_config_update({'ai_enabled':False})
        self.assertEqual(cleaned,{'ai_enabled':False})
        self.assertIsNone(errors)
        self.assertIsNotNone(validate_general_config_update([])[1])

    @patch('apps.products.services.discovery_service.search_product_embeddings')
    @patch('apps.products.services.discovery_service.ProductService.get_public_variant_products')
    def test_keyword_matches_skip_provider(self, products, semantic):
        products.return_value=([{'id':'a'}],1,{})
        self.assertEqual(search_catalog('sofa'),(*products.return_value, 'matching'))
        semantic.assert_not_called()

    @patch('apps.products.services.discovery_service.search_product_embeddings')
    @patch('apps.products.services.discovery_service.ProductService.get_public_variant_products')
    def test_semantic_candidates_use_public_selector_and_pagination(self, products, semantic):
        products.side_effect=[([],0,{}),([{'id':'a'}],1,{})]
        semantic.return_value=[{'product_id':'a'}]
        result = search_catalog('a comfy place to sit',page=2,limit=4)
        self.assertEqual(result[1],1)
        self.assertEqual(result[3],'related')
        products.assert_called_with(
            product_ids=['a'], preserve_order=True, include_product_title=True,
            page=2, limit=4,
        )

    @patch('apps.products.services.discovery_service.search_product_embeddings',side_effect=RuntimeError('offline'))
    @patch('apps.products.services.discovery_service.ProductService.get_public_variant_products',return_value=([],0,{}))
    def test_provider_failure_preserves_keyword_response(self, products, semantic):
        with self.assertLogs('apps.products.services.discovery_service',level='ERROR'):
            self.assertEqual(search_catalog('comfy'),([],0,{},'none'))

    @patch('apps.products.services.discovery_service.search_product_embeddings')
    @patch('apps.products.services.discovery_service.ProductService.get_public_variant_products',return_value=([],0,{}))
    def test_disabled_storefront_semantic_search_never_calls_provider(self, products, semantic):
        self.storefront_flag.return_value=False
        self.assertEqual(search_catalog('sofa'),([],0,{},'none'))
        semantic.assert_not_called()

    @patch('apps.ai_assistant.features.GeneralConfig.get')
    @patch('apps.ai_assistant.embeddings.search.get_cached_query_embedding', side_effect=RuntimeError('provider reached'))
    def test_agent_semantics_independent_of_storefront_switch(self, embedding, config):
        from apps.ai_assistant.embeddings.search import search_product_embeddings
        config.return_value=SimpleNamespace(ai_enabled=True, ai_semantic_search_enabled=False,
            ai_shopper_enabled=True, ai_guest_enabled=True, ai_discovery_enabled=True)
        tools=[SimpleNamespace(name='search_products')]
        for agent in ('shopper','guest'):
            self.assertEqual(available_tools(tools,agent),tools)
        with self.assertRaisesRegex(RuntimeError,'provider reached'):
            search_product_embeddings('sofa')
        embedding.assert_called_once_with('sofa')
