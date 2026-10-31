from django.db import models

CATEGORIES = [
    ("road_damage", "Road damage / pothole"),
    ("water_leak", "Water leak / pipe burst"),
    ("garbage", "Garbage / waste"),
    ("streetlight", "Streetlight not working"),
    ("drainage", "Drainage / sewage overflow"),
    ("other", "Other / unclear"),
]
CATEGORY_KEYS = [c[0] for c in CATEGORIES]


class Ward(models.Model):
    """Administrative ward. `geometry` is a GeoJSON Polygon/MultiPolygon geometry object."""

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True)
    geometry = models.JSONField()
    source_url = models.URLField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Authority(models.Model):
    """A department responsible for some categories. `jurisdiction` null means the whole pilot area."""

    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    categories = models.JSONField(default=list, help_text="List of category keys handled")
    jurisdiction = models.JSONField(null=True, blank=True, help_text="GeoJSON geometry; empty = whole pilot area")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    source_url = models.URLField(blank=True, help_text="Official page this entry was verified from")
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "authorities"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ContactChannel(models.Model):
    EMAIL, FORM, API = "email", "form", "api"
    TYPES = [(EMAIL, "Email"), (FORM, "Published web form"), (API, "API (Open311-style)")]

    authority = models.ForeignKey(Authority, on_delete=models.CASCADE, related_name="channels")
    type = models.CharField(max_length=10, choices=TYPES, default=EMAIL)
    address = models.CharField(max_length=300, help_text="Email address, form URL or API endpoint")
    verified_at = models.DateTimeField(null=True, blank=True, help_text="Set only after a real test succeeded")
    verification_note = models.TextField(blank=True)
    priority = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["priority", "id"]

    def __str__(self):
        return f"{self.authority.name}: {self.address}"
