import secrets

from django.db import models
from django.utils import timezone

from apps.authorities.models import Authority, ContactChannel


def new_token():
    return secrets.token_urlsafe(24)


class Dispatch(models.Model):
    PENDING, SENT, FAILED = "pending", "sent", "failed"

    report = models.ForeignKey("reports.Report", on_delete=models.CASCADE, related_name="dispatches")
    authority = models.ForeignKey(Authority, on_delete=models.PROTECT)
    channel = models.ForeignKey(ContactChannel, null=True, blank=True, on_delete=models.SET_NULL)
    recipient = models.CharField(max_length=300, blank=True, help_text="Actual address used (sandbox or live)")
    mode = models.CharField(max_length=10, default="sandbox")
    subject = models.CharField(max_length=300, blank=True)
    body = models.TextField(blank=True)
    delivery_status = models.CharField(max_length=10, default=PENDING)
    error = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    ack_token = models.CharField(max_length=64, unique=True, default=new_token)
    escalated_from = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="escalations")
    created_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
