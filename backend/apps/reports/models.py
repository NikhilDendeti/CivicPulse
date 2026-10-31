import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.authorities.models import CATEGORIES, Authority, Ward

SEVERITY_LEVELS = [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")]
SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class Status:
    SUBMITTED = "submitted"
    ANALYSING = "analysing"
    NEEDS_INFO = "needs_info"        # waiting on a clarifying answer from the citizen
    NEEDS_REVIEW = "needs_review"    # waiting on a human moderator
    ANALYSED = "analysed"            # analysis done, waiting on citizen confirmation
    MERGED = "merged"                # attached to an existing issue cluster
    ROUTED = "routed"
    SENT = "sent"
    DISPATCH_FAILED = "dispatch_failed"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISPUTED = "disputed"
    REOPENED = "reopened"
    REJECTED = "rejected"

    CHOICES = [
        (v, v.replace("_", " ").title())
        for k, v in vars().items()
        if k.isupper() and isinstance(v, str)
    ]
    OPEN = [SUBMITTED, ANALYSING, NEEDS_INFO, NEEDS_REVIEW, ANALYSED, MERGED, ROUTED, SENT,
            DISPATCH_FAILED, ACKNOWLEDGED, IN_PROGRESS, DISPUTED, REOPENED]
    CLOSED = [RESOLVED, REJECTED]


def new_ref():
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    while True:
        ref = "CP-HYD-" + "".join(secrets.choice(alphabet) for _ in range(6))
        if not Report.objects.filter(ref_no=ref).exists():
            return ref


def _path(kind, instance, filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"{kind}/{instance.ref_no}-{secrets.token_hex(4)}.{ext}"


def upload_img(instance, filename):
    return _path("img", instance, filename)


def upload_aud(instance, filename):
    return _path("aud", instance, filename)


def upload_vid(instance, filename):
    return _path("vid", instance, filename)


class IssueCluster(models.Model):
    category = models.CharField(max_length=20, choices=CATEGORIES)
    lat = models.FloatField()
    lng = models.FloatField()
    affected_count = models.PositiveIntegerField(default=1)
    canonical = models.ForeignKey("Report", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Cluster {self.pk} ({self.category}, {self.affected_count})"


class Report(models.Model):
    ref_no = models.CharField(max_length=20, unique=True, default=new_ref)
    device_token = models.CharField(max_length=64, blank=True, db_index=True)
    citizen_email = models.EmailField(blank=True)
    consent = models.BooleanField(default=False)
    lang = models.CharField(max_length=5, default="en")

    image = models.ImageField(upload_to=upload_img, blank=True)
    audio = models.FileField(upload_to=upload_aud, blank=True)
    video = models.FileField(upload_to=upload_vid, blank=True)
    text = models.TextField(blank=True)
    transcript_orig = models.TextField(blank=True)
    transcript_en = models.TextField(blank=True)

    lat = models.FloatField()
    lng = models.FloatField()
    accuracy_m = models.FloatField(null=True, blank=True)
    address = models.CharField(max_length=500, blank=True)
    ward = models.ForeignKey(Ward, null=True, blank=True, on_delete=models.SET_NULL)
    ward_label = models.CharField(max_length=200, blank=True, db_index=True,
                                  help_text="Ward polygon name, else locality from reverse geocoding")

    category = models.CharField(max_length=20, choices=CATEGORIES, blank=True)
    severity_score = models.PositiveSmallIntegerField(null=True, blank=True)
    severity_level = models.CharField(max_length=10, choices=SEVERITY_LEVELS, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    rationale = models.TextField(blank=True)
    description = models.TextField(blank=True)
    factors = models.JSONField(default=list, blank=True)
    clarifying_question = models.TextField(blank=True)
    citizen_answer = models.TextField(blank=True)
    ai_error = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=Status.CHOICES, default=Status.SUBMITTED, db_index=True)
    cluster = models.ForeignKey(IssueCluster, null=True, blank=True, on_delete=models.SET_NULL, related_name="reports")
    embedding = models.JSONField(null=True, blank=True)
    phash = models.CharField(max_length=32, blank=True)
    authenticity_flags = models.JSONField(default=list, blank=True)

    authority = models.ForeignKey(Authority, null=True, blank=True, on_delete=models.SET_NULL, related_name="reports")
    routing_reason = models.TextField(blank=True)
    routing_confidence = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.ref_no

    def set_status(self, status, actor="system", note="", proof=None, save=True):
        self.status = status
        if save:
            self.save(update_fields=["status", "updated_at"])
        ev = StatusEvent.objects.create(report=self, status=status, actor=actor, note=note)
        if proof:
            ev.proof = proof
            ev.save(update_fields=["proof"])
        return ev


class StatusEvent(models.Model):
    """Append-only timeline; doubles as the audit log."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=20)
    actor = models.CharField(max_length=40, default="system")
    note = models.TextField(blank=True)
    proof = models.ImageField(upload_to="proof/", blank=True)
    at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["at", "id"]


class ModerationAction(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="moderation_actions")
    field = models.CharField(max_length=40)
    old_value = models.CharField(max_length=300, blank=True)
    new_value = models.CharField(max_length=300, blank=True)
    reason = models.TextField(blank=True)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    at = models.DateTimeField(default=timezone.now)
