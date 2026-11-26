"""Create the approved Amammre Wears journal articles."""
import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify
from apps.blog.models import BlogCategory, BlogPost

POSTS = [{'title': 'A guide to Ghanaian traditional wear',
  'category_name': 'Heritage & Culture',
  'excerpt': 'From kente cloth to the northern smock, discover some of the pieces that make Ghanaian fashion '
             'so expressive.',
  'content': '<p>Ghanaian fashion brings together cloth, craftsmanship, and personal style. What you wear '
             'can reflect an occasion, a community, or simply the colours and silhouettes you love. Here are '
             'a few places to begin exploring.</p>\n'
             '<h2>Kente: cloth with character</h2>\n'
             '<p>Kente is a woven textile made from narrow strips joined together. Its colours and patterns '
             'make it a striking choice for celebrations, but it can also inspire contemporary clothing and '
             'accessories. When shopping, check how a piece is made: handwoven kente and printed fabrics '
             'inspired by kente have different qualities.</p>\n'
             '<h2>Fugu and batakari</h2>\n'
             '<p>The northern smock is known by names including fugu and batakari. Traditionally made from '
             'strips of woven fabric, smocks can be worn for ceremonies and everyday occasions. Today you '
             'can find them in a variety of cuts, colours, and styles.</p>\n'
             '<h2>Kaba and slit</h2>\n'
             '<p>A kaba and slit pairs a blouse with a skirt, often made from matching fabric. The '
             'silhouette offers plenty of room for individual expression, from a classic combination to a '
             'modern interpretation.</p>\n'
             '<h2>Make it your own</h2>\n'
             '<p>Start with a piece you feel comfortable in and consider where you will wear it. A '
             'meaningful garment becomes even more special when you find your own way to style it.</p>',
  'cover_image_url': 'https://alisad.net/wp-content/uploads/2025/07/kpetoe.jpg'},
 {'title': 'How to style African print for everyday wear',
  'category_name': 'Style Guides',
  'excerpt': 'A few simple ways to bring colour and print into your everyday wardrobe.',
  'content': '<p>A bold print can be the starting point for a look that feels entirely your own. You '
             'don&#x27;t need a special occasion to enjoy it: a shirt, a skirt, or even a small accessory '
             'can make an everyday outfit feel considered.</p>\n'
             '<h2>Start with one piece</h2>\n'
             '<p>Choose a printed shirt, dress, or pair of trousers and pair it with pieces you already '
             'enjoy wearing. A plain top or neutral trousers can give the print room to stand out.</p>\n'
             '<h2>Pick a colour from the print</h2>\n'
             '<p>Look closely at the pattern and choose one colour to repeat in a bag, shoe, or piece of '
             'jewellery. The connection can bring the outfit together without making it feel too '
             'coordinated.</p>\n'
             '<h2>Dress for your day</h2>\n'
             '<p>For a relaxed look, try comfortable footwear and simple accessories. For an evening or '
             'special event, add a structured bag or jewellery you love. The same piece can take on a '
             'different feel with a few thoughtful changes.</p>\n'
             '<h2>Choose comfort first</h2>\n'
             '<p>Fit, fabric, and how you feel matter as much as the print. Pick pieces you can move in and '
             'will want to wear again.</p>',
  'cover_image_url': 'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=1400&q=85'},
 {'title': 'Choosing an outfit for a Ghanaian celebration',
  'category_name': 'Occasions',
  'excerpt': 'Think about the event, comfort, and finishing touches when choosing what to wear for a '
             'celebration.',
  'content': '<p>Weddings, engagements, festivals, and family gatherings are opportunities to dress with '
             'joy. The best outfit is one that suits the occasion and lets you feel comfortable throughout '
             'the day.</p>\n'
             '<h2>Begin with the invitation</h2>\n'
             '<p>Check whether the event has a dress code, colour palette, or fabric chosen by the hosts. If '
             'you&#x27;re unsure, ask ahead—especially for a ceremony where family or community customs are '
             'important.</p>\n'
             '<h2>Choose your silhouette</h2>\n'
             '<p>A kaba and slit, smock, dress, coordinated set, or draped cloth can each be a beautiful '
             'choice. Consider how long you&#x27;ll be sitting, standing, travelling, or dancing when '
             'deciding on the fit.</p>\n'
             '<h2>Think about the details</h2>\n'
             '<p>Headwraps, caps, bags, footwear, and jewellery can complete a look. Pick a few pieces that '
             'complement the outfit and feel comfortable for the occasion.</p>\n'
             '<h2>Give yourself time</h2>\n'
             '<p>If your outfit needs alterations or special care, plan ahead. A little preparation gives '
             'you more time to enjoy the celebration and the people around you.</p>',
  'cover_image_url': 'https://images.unsplash.com/photo-1496747611176-843222e1e57c?auto=format&fit=crop&w=1400&q=85'}]


class Command(BaseCommand):
    help = "Create approved Amammre journal posts without overwriting existing posts."

    def handle(self, *args, **options):
        if os.environ.get("ESTORE_ENV_FILE") != ".env.amammre":
            raise CommandError("Run this command with manage_store.py amammre.")
        with transaction.atomic():
            for data in POSTS:
                category, _ = BlogCategory.objects.get_or_create(
                    slug=slugify(data["category_name"]), defaults={"name": data["category_name"]}
                )
                post, created = BlogPost.objects.get_or_create(
                    slug=slugify(data["title"]),
                    defaults={"title": data["title"], "excerpt": data["excerpt"], "content": data["content"],
                              "cover_image_url": data["cover_image_url"], "category": category,
                              "author_name": "Amammre Wears", "status": BlogPost.STATUS_PUBLISHED},
                )
                self.stdout.write(f"{'Created' if created else 'Already exists'}: {post.title}")
