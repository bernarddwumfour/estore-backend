from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ai_assistant import signals, tasks


class EmbeddingRefreshTests(SimpleTestCase):
    @patch("apps.ai_assistant.signals.refresh_product_embedding.delay")
    @patch("apps.ai_assistant.signals.transaction.on_commit")
    def test_product_and_variant_changes_schedule_after_commit(self, on_commit, delay):
        product = SimpleNamespace(pk="product-id")
        variant = SimpleNamespace(product_id="product-id")
        signals.product_saved(None, product, "default")
        signals.variant_saved(None, variant, "default")
        signals.variant_deleted(None, variant, "default")
        self.assertEqual(on_commit.call_count, 3)
        delay.assert_not_called()
        for call in on_commit.call_args_list:
            self.assertEqual(call.kwargs["using"], "default")
            call.args[0]()
        self.assertEqual(delay.call_count, 3)
        delay.assert_called_with("product-id")

    @patch("apps.ai_assistant.signals.refresh_product_embedding.delay", side_effect=RuntimeError("broker unavailable"))
    @patch("apps.ai_assistant.signals.transaction.on_commit", side_effect=lambda callback, using: callback())
    def test_enqueue_failure_does_not_break_catalog_save(self, on_commit, delay):
        with self.assertLogs("apps.ai_assistant.signals", level="ERROR"):
            signals.product_saved(None, SimpleNamespace(pk="id"), "default")

    @patch("apps.ai_assistant.embeddings.indexer.index_product", return_value={"status": "indexed"})
    def test_refresh_calls_indexer(self, index_product):
        self.assertEqual(tasks.refresh_product_embedding.run("id"), {"status": "indexed"})
        index_product.assert_called_once_with("id")

    @patch("apps.ai_assistant.tasks.refresh_product_embedding.delay")
    @patch("apps.ai_assistant.models.ProductEmbedding.objects")
    @patch("apps.products.models.Product.objects")
    def test_reconciliation_removes_unpublished_and_queues_published(self, products, embeddings, delay):
        products.filter.return_value.values_list.return_value.iterator.return_value = iter(["a", "b"])
        self.assertEqual(tasks.reconcile_product_embeddings.run(), {"queued": 2})
        embeddings.exclude.return_value.delete.assert_called_once()
        self.assertEqual(delay.call_count, 2)
