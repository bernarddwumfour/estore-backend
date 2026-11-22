from datetime import timedelta
from django.test import TestCase, RequestFactory, override_settings
from django.core.cache import cache
from apps.users.bff_middleware import BFFMiddleware
from apps.users.decorators.auth import jwt_optional
from estore.utils.responses import APIResponse
from django.utils import timezone
from apps.users.models.browser_session import BrowserSession
from apps.users.services.browser_session_service import create_session, delete_session, resolve_session
from apps.users.tests.factories import make_user, make_affiliate
from apps.users.utils.token_utils import generate_jwt_token


@override_settings(BFF_SHARED_SECRET='test-bff-secret', RATELIMIT_ENABLE=False)
class BrowserSessionTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.token = create_session(self.user)
        self.headers = {'HTTP_X_BFF_KEY': 'test-bff-secret', 'HTTP_X_BFF_SESSION': self.token}

    def test_only_hash_is_stored_and_profile_works(self):
        row = BrowserSession.objects.get()
        self.assertNotEqual(row.digest, self.token)
        self.assertEqual(len(row.digest), 64)
        response = self.client.get('/api/users/profile', **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['id'], str(self.user.id))

    def test_session_requires_bff_authentication(self):
        self.assertEqual(self.client.get('/api/users/profile', HTTP_X_BFF_SESSION=self.token).status_code, 401)
        self.assertEqual(self.client.get('/api/users/profile', **{**self.headers, 'HTTP_X_BFF_KEY': 'wrong'}).status_code, 403)
        with override_settings(BFF_SHARED_SECRET=''):
            self.assertEqual(self.client.get('/api/users/profile', **self.headers).status_code, 403)

    def test_expired_disabled_and_password_changed_sessions_are_rejected(self):
        BrowserSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(resolve_session(self.token))
        self.token = create_session(self.user)
        self.user.is_active = False
        self.user.save()
        self.assertIsNone(resolve_session(self.token))
        self.user.is_active = True
        self.user.set_password('New-Strong-Pass123!')
        self.user.save()
        self.assertIsNone(resolve_session(self.token))

    def test_logout_deletes_session_and_replay_fails(self):
        response = self.client.post('/api/users/logout', {}, content_type='application/json', **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BrowserSession.objects.exists())
        self.assertEqual(self.client.get('/api/users/profile', **self.headers).status_code, 401)

    def test_role_enforcement_uses_database(self):
        response = self.client.get('/api/users/admin/users', **self.headers)
        # Choose an existing protected endpoint; customers must never pass its role check.
        self.assertEqual(response.status_code, 403)

    def test_login_returns_session_only_to_bff(self):
        payload = {'email': self.user.email, 'password': 'Str0ng-Pass!23'}
        response = self.client.post('/api/users/login', payload, content_type='application/json', HTTP_X_BFF_KEY='test-bff-secret')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertNotIn('tokens', data)
        self.assertIsNotNone(resolve_session(data['session_id']))

    def test_legacy_bearer_clients_still_work(self):
        response = self.client.get('/api/users/profile', HTTP_AUTHORIZATION=f'Bearer {generate_jwt_token(self.user)}')
        self.assertEqual(response.status_code, 200)

    def test_invalid_identifiers_and_deletion(self):
        for value in [None, '', [], 'x' * 1000]:
            self.assertIsNone(resolve_session(value))
        delete_session(self.token)
        delete_session(self.token)
        self.assertIsNone(resolve_session(self.token))

    def test_cache_loss_does_not_restore_a_deleted_session(self):
        delete_session(self.token)
        cache.clear()
        self.assertIsNone(resolve_session(self.token))

    def test_optional_auth_and_live_role_changes(self):
        @jwt_optional
        def view(request):
            return APIResponse.success({"user_id": str(request.user.id) if request.user else None})
        request = RequestFactory().get('/api/example', **self.headers)
        response = BFFMiddleware(view)(request)
        self.assertContains(response, str(self.user.id))
        self.user.role = "staff"
        self.user.save()
        self.assertEqual(resolve_session(self.token).user.role, "staff")

    def test_malformed_login_is_bad_request(self):
        for payload in [[], 3, {"email": [], "password": "x"}]:
            response = self.client.post('/api/users/login', payload, content_type='application/json', HTTP_X_BFF_KEY='test-bff-secret')
            self.assertEqual(response.status_code, 400)

    def test_restored_session_preserves_affiliate_navigation(self):
        make_affiliate(user=self.user)
        response = self.client.get('/api/users/profile', **self.headers)
        self.assertTrue(response.json()['data']['is_affiliate'])
