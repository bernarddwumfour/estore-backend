import uuid

from apps.marketing.models import EmailCampaign
from apps.products.tests.factories import make_admin, make_user  # noqa: F401
from apps.users.models import CustomerProfile


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def make_customer_profile(user=None, **kwargs) -> CustomerProfile:
    user = user or make_user()
    return CustomerProfile.objects.create(user=user, **kwargs)


def make_campaign(created_by=None, **kwargs) -> EmailCampaign:
    defaults = {
        "name": _unique("Campaign"),
        "subject": "Hello from the store",
        "html_body": "<p>Big news!</p>",
        "campaign_type": EmailCampaign.TYPE_NEWSLETTER,
        "segment": EmailCampaign.SEGMENT_ALL_USERS,
    }
    defaults.update(kwargs)
    return EmailCampaign.objects.create(created_by=created_by, **defaults)
