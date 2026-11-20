from estore.utils.responses import APIResponse
from io import BytesIO
from PIL import Image, UnidentifiedImageError
from apps.templates.models import TemplateAsset
from .common import endpoint
from apps.templates.selectors.template_selectors import page, template_queryset

@endpoint(['POST'])
def assets(request):
    upload = request.FILES.get('image')
    if not upload or upload.size > 10 * 1024 * 1024:
        raise ValueError('Choose an image smaller than 10 MB.')
    try:
        with Image.open(BytesIO(upload.read())) as image:
            if image.format not in ('PNG', 'JPEG', 'WEBP', 'GIF'):
                raise ValueError('Choose a PNG, JPEG, WebP or GIF image.')
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError('This image cannot be read.')
    upload.seek(0)
    obj = TemplateAsset.objects.create(image=upload, created_by=request.user)
    return APIResponse.created({'asset': {'id': str(obj.id), 'url': request.build_absolute_uri(obj.image.url)}})
