# apps/products/migrations/0003_add_analytics_indexes.py
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0002_category_is_hidden'),  # This matches your existing migration
    ]

    operations = [
        # Add indexes for better analytics performance
        migrations.AddIndex(
            model_name='product',
            index=models.Index(
                fields=['status', 'created_at'],
                name='idx_products_status_created'
            ),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(
                fields=['is_featured', 'is_bestseller', 'is_new'],
                name='idx_products_flags'
            ),
        ),
        migrations.AddIndex(
            model_name='productvariant',
            index=models.Index(
                fields=['stock', 'price'],
                name='idx_variants_stock_price'
            ),
        ),
        migrations.AddIndex(
            model_name='productreview',
            index=models.Index(
                fields=['rating', 'is_approved'],
                name='idx_reviews_rating_approved'
            ),
        ),
        migrations.AddIndex(
            model_name='category',
            index=models.Index(
                fields=['is_hidden', 'is_active'],
                name='idx_categories_hidden_active'
            ),
        ),
    ]