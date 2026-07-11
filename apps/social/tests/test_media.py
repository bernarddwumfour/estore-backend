import shutil
import tempfile

from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from apps.social.models import SocialMedia
from apps.social.tests.factories import make_admin, make_user
from apps.users.utils.token_utils import generate_jwt_token

# 1x1 transparent GIF
GIF_BYTES = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D"
    b"\x01\x00;"
)


class SocialMediaLibraryTests(TestCase):
    """Uses a temp local storage so tests never touch Cloudinary."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._tmp_media = tempfile.mkdtemp(prefix="social-media-tests-")
        field = SocialMedia._meta.get_field("file")
        cls._real_storage = field.storage
        field.storage = FileSystemStorage(location=cls._tmp_media)

    @classmethod
    def tearDownClass(cls):
        SocialMedia._meta.get_field("file").storage = cls._real_storage
        shutil.rmtree(cls._tmp_media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.client = Client()
        self.admin = make_admin()
        self.user = make_user()

    def _auth(self, user=None):
        token = generate_jwt_token(user or self.admin)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def _upload(self, filename, content=GIF_BYTES, content_type="image/gif"):
        return self.client.post(
            "/api/social/admin/media/upload",
            {"file": SimpleUploadedFile(filename, content, content_type=content_type)},
            **self._auth(),
        )

    def test_upload_image(self):
        response = self._upload("banner.gif")
        self.assertEqual(response.status_code, 201)
        data = response.json()["data"]
        self.assertEqual(data["media_type"], "image")
        self.assertEqual(data["name"], "banner.gif")
        self.assertTrue(data["url"])
        self.assertEqual(SocialMedia.objects.count(), 1)

    def test_upload_video(self):
        response = self._upload("clip.mp4", b"fake-video-bytes", "video/mp4")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["data"]["media_type"], "video")

    def test_upload_invalid_extension(self):
        response = self._upload("malware.exe", b"nope", "application/octet-stream")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SocialMedia.objects.count(), 0)

    def test_upload_oversize_image(self):
        big = b"x" * (5 * 1024 * 1024 + 1)
        response = self._upload("huge.png", big, "image/png")
        self.assertEqual(response.status_code, 400)

    def test_upload_requires_file(self):
        response = self.client.post("/api/social/admin/media/upload", {}, **self._auth())
        self.assertEqual(response.status_code, 400)

    def test_upload_requires_admin(self):
        response = self.client.post(
            "/api/social/admin/media/upload",
            {"file": SimpleUploadedFile("a.png", GIF_BYTES)},
            **self._auth(self.user),
        )
        self.assertEqual(response.status_code, 403)

    def test_list_with_filter_and_search(self):
        self._upload("summer-banner.gif")
        self._upload("promo.mp4", b"v", "video/mp4")

        response = self.client.get("/api/social/admin/media", **self._auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["total"], 2)

        response = self.client.get(
            "/api/social/admin/media?media_type=video", **self._auth()
        )
        self.assertEqual(response.json()["data"]["total"], 1)

        response = self.client.get(
            "/api/social/admin/media?search=summer", **self._auth()
        )
        self.assertEqual(response.json()["data"]["total"], 1)
        self.assertEqual(response.json()["data"]["media"][0]["name"], "summer-banner.gif")

    def test_delete_media(self):
        self._upload("gone.gif")
        media_id = str(SocialMedia.objects.get().id)
        response = self.client.delete(
            f"/api/social/admin/media/{media_id}/delete", **self._auth()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SocialMedia.objects.count(), 0)

    def test_delete_missing_media(self):
        response = self.client.delete(
            "/api/social/admin/media/00000000-0000-0000-0000-000000000000/delete",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 404)
