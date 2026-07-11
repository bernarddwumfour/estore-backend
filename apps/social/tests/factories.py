import uuid

from apps.products.tests.factories import make_admin, make_user  # noqa: F401
from apps.social.models import SocialPost


def make_social_post(created_by=None, **kwargs) -> SocialPost:
    defaults = {
        "source": SocialPost.SOURCE_MANUAL,
        "caption": f"Test caption {uuid.uuid4().hex[:8]}",
        "platforms": [{"platform": "twitter", "accountId": "acc_test"}],
        "status": SocialPost.STATUS_PENDING_APPROVAL,
    }
    defaults.update(kwargs)
    return SocialPost.objects.create(created_by=created_by, **defaults)


ZERNIO_ACCOUNTS = [
    {"_id": "acc_tw", "platform": "twitter", "name": "Store Twitter"},
    {"_id": "acc_ig", "platform": "instagram", "name": "Store Instagram"},
]
