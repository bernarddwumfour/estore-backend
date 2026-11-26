"""Exercise storage selection in fresh Django processes without provider access."""
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class MediaStorageConfigurationTests(unittest.TestCase):
    def run_settings(self, provider, **values):
        env = os.environ.copy()
        env.pop("ESTORE_ENV_FILE", None)
        env.update({
            "DJANGO_SETTINGS_MODULE": "estore.settings",
            "SECRET_KEY": "test-only-key",
            "MEDIA_STORAGE_BACKEND": provider,
            "AWS_EC2_METADATA_DISABLED": "true",
            **values,
        })
        return subprocess.run(
            [sys.executable, "-c", (
                "import django; django.setup(); "
                "from django.core.files.storage import default_storage; "
                "from apps.social.models import _social_media_storage; "
                "print(type(default_storage._wrapped).__name__ if default_storage._wrapped.__class__.__name__ != 'object' else type(default_storage).__name__); "
                "print(type(_social_media_storage()).__name__); "
                "print(default_storage.url('example.png'))"
            )],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
        )

    def test_local_storage_serves_absolute_media_url(self):
        result = self.run_settings("local", MEDIA_URL="http://localhost:8004/media/")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("http://localhost:8004/media/example.png", result.stdout)
        self.assertIn("DefaultStorage", result.stdout)

    def test_s3_endpoint_generates_signed_url_and_social_uses_default(self):
        result = self.run_settings(
            "s3", AWS_STORAGE_BUCKET_NAME="test-bucket", AWS_S3_ENDPOINT_URL="https://storage.example.com",
            AWS_S3_REGION_NAME="us-east-1", AWS_S3_ADDRESSING_STYLE="path",
            AWS_ACCESS_KEY_ID="test-access-key", AWS_SECRET_ACCESS_KEY="test-secret-key", AWS_QUERYSTRING_AUTH="True",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("https://storage.example.com/test-bucket/example.png?", result.stdout)
        self.assertIn("DefaultStorage", result.stdout)

    def test_s3_requires_bucket(self):
        result = self.run_settings("s3", AWS_STORAGE_BUCKET_NAME="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AWS_STORAGE_BUCKET_NAME is required", result.stderr)

    def test_cloudinary_keeps_raw_social_storage(self):
        result = self.run_settings("cloudinary")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("RawMediaCloudinaryStorage", result.stdout)

    def test_invalid_provider_is_rejected(self):
        result = self.run_settings("unknown")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MEDIA_STORAGE_BACKEND must be", result.stderr)
