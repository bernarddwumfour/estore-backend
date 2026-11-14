"""Seed the initial Ghana-focused TyrePapa blog posts."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.blog.models import BlogCategory, BlogPost


POSTS = [
    {
        "title": "How Ghana's Rainy Season Changes the Way Your Tyres Grip",
        "slug": "ghana-rainy-season-tyre-grip",
        "cover_image_url": "https://res.cloudinary.com/qrctmxnb/image/upload/v1794530764/tyrepapa/blog/ghana-rainy-season-tyre-grip.png",
        "excerpt": (
            "Wet roads, standing water and worn tread can change your stopping distance. "
            "Here is how to keep your car planted through Ghana's rainy season."
        ),
        "content": """
<p>Ghana's rainy season can turn a familiar commute into a very different drive. Water, mud and polished road surfaces reduce the grip available between your tyres and the road, especially around standing water in low-lying areas.</p>
<h2>Start with the tread</h2>
<p>The grooves in a tyre move water away from the contact patch. Check that the tread is not close to its wear indicators and look for stones or other debris lodged in the grooves. A tyre that looks acceptable at a glance may still be too worn for confident wet-weather braking.</p>
<h2>Slow down before the water</h2>
<p>Reduce speed smoothly when you see a flooded section, avoid harsh steering inputs and leave extra space for the vehicle ahead. If the steering suddenly feels light, ease off the accelerator rather than braking or turning sharply.</p>
<h2>Check all four tyres</h2>
<p>Uneven wear, cracks or a difference in pressure between the tyres can make the car pull or feel unsettled on wet roads. Inspect the tyres when they are cold and replace any tyre with a bulge or serious sidewall damage.</p>
<p>Good tread, correct pressure and a little more following distance make rainy-season driving safer on roads across Accra, Kumasi, Takoradi and beyond.</p>
""".strip(),
        "meta_title": "Tyre Grip and Safe Driving in Ghana's Rainy Season | TyrePapa",
        "meta_description": "Practical tyre and wet-road safety tips for driving through Ghana's rainy season.",
    },
    {
        "title": "The Right Tyre Pressure for Accra Commutes and Ghanaian Roads",
        "slug": "tyre-pressure-ghana-accra-commutes",
        "cover_image_url": "https://res.cloudinary.com/qrctmxnb/image/upload/v1794530770/tyrepapa/blog/tyre-pressure-ghana-accra-commutes.png",
        "excerpt": (
            "Correct tyre pressure improves handling, comfort and fuel economy. Learn what to "
            "check before an Accra commute or a long Ghana road trip."
        ),
        "content": """
<p>Tyre pressure affects how your car brakes, steers and uses fuel. It also matters on Ghana's mix of city streets, highways, rough patches and unpaved roads.</p>
<h2>Use your vehicle's recommended pressure</h2>
<p>The correct figure is usually printed on the driver's door-jamb sticker, inside the fuel flap or in the owner's manual. Use that recommendation rather than the maximum pressure moulded into the tyre sidewall. Front and rear pressures may be different, and the loaded-vehicle setting may be different from the everyday setting.</p>
<h2>Check when the tyres are cold</h2>
<p>Measure pressure before a long drive, ideally before the car has been in the sun or driven for more than a few kilometres. Check the spare as well. A slow leak, a bent wheel or a damaged valve can cause one tyre to lose pressure repeatedly.</p>
<h2>Adjust for the journey, not the pothole</h2>
<p>Do not deliberately underinflate tyres to soften bumps. Too little pressure increases heat and sidewall flex, while too much pressure reduces the contact patch. Carry the recommended load, slow down for potholes and have the tyres inspected after a hard impact.</p>
<p>A quick pressure check can make daily driving in Accra more predictable and help your tyres wear evenly on longer journeys between towns.</p>
""".strip(),
        "meta_title": "Tyre Pressure Guide for Accra and Ghana | TyrePapa",
        "meta_description": "How to check and maintain the correct tyre pressure for Ghanaian roads and everyday driving.",
    },
    {
        "title": "When Should You Replace Your Tyres in Ghana?",
        "slug": "when-to-replace-tyres-in-ghana",
        "cover_image_url": "https://res.cloudinary.com/qrctmxnb/image/upload/v1794530773/tyrepapa/blog/when-to-replace-tyres-in-ghana.png",
        "excerpt": (
            "Tread wear is only one warning sign. Learn when cracks, bulges, uneven wear and "
            "age mean it is time for a new set of tyres."
        ),
        "content": """
<p>Tyres work hard in Ghana's heat, traffic and changing road conditions. Waiting for a puncture is not a reliable replacement plan; inspect them regularly and act when you see signs of deterioration.</p>
<h2>Look for these warning signs</h2>
<ul>
  <li>Tread is at or close to the built-in wear indicators.</li>
  <li>Cracks appear on the sidewall or between the tread blocks.</li>
  <li>A bulge, cut or exposed cord is visible after an impact.</li>
  <li>The tread is wearing more on one edge, or the car vibrates or pulls.</li>
</ul>
<h2>Age matters too</h2>
<p>Rubber hardens over time, even when a tyre has travelled only a few kilometres. Check the date code on the sidewall and ask a tyre professional to assess older tyres, especially if the vehicle spends much of its time parked outdoors in the heat.</p>
<h2>Replace safely</h2>
<p>Replace damaged tyres immediately and use the correct size, load rating and speed rating for your vehicle. If replacing fewer than four tyres, ask a qualified fitter where the newer pair should be placed and have the wheels balanced and aligned.</p>
<p>When you are unsure, a professional inspection is cheaper than guessing with the only part of the car that touches the road.</p>
""".strip(),
        "meta_title": "When to Replace Your Tyres in Ghana | TyrePapa",
        "meta_description": "The key tread, age and damage warning signs that mean your tyres should be replaced in Ghana.",
    },
]


class Command(BaseCommand):
    help = "Create or update the initial Ghana-focused TyrePapa blog posts."

    def handle(self, *args, **options):
        category, _ = BlogCategory.objects.get_or_create(
            slug="tyre-care",
            defaults={
                "name": "Tyre Care",
                "description": "Practical tyre, maintenance and road-safety advice for Ghanaian drivers.",
            },
        )

        for post_data in POSTS:
            post, created = BlogPost.objects.update_or_create(
                slug=post_data["slug"],
                defaults={
                    **post_data,
                    "category": category,
                    "author_name": "TyrePapa",
                    "status": BlogPost.STATUS_PUBLISHED,
                    "published_at": timezone.now(),
                    "is_featured": False,
                },
            )
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action}: {post.title}"))

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(POSTS)} TyrePapa blog posts."))
