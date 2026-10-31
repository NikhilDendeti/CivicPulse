"""Complaint generation and delivery (FR-12, FR-13). Only real, permitted channels are used:
email is automated; form/API channels are recorded but never claimed as delivered."""
import logging
import time

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from apps.authorities.models import CATEGORIES, ContactChannel
from apps.reports.models import Report, Status

from .models import Dispatch

log = logging.getLogger(__name__)
CATEGORY_LABEL = dict(CATEGORIES)
MAX_ATTEMPTS = 3


def media_url(f):
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}{f.url}" if f else ""


def build_complaint(report, dispatch, reason=""):
    cluster = report.cluster
    affected = cluster.affected_count if cluster else 1
    lines = [
        f"CivicPulse complaint {report.ref_no}",
        "",
        f"Issue: {CATEGORY_LABEL.get(report.category, report.category)}",
        f"Severity: {report.severity_level.upper()} ({report.severity_score}/100, AI confidence {report.confidence:.0%})"
        if report.confidence is not None and report.severity_score is not None else "Severity: not scored",
        f"Description: {report.description or report.text}",
        f"Why this severity: {report.rationale}",
        f"Location: {report.address or 'not available'}  ({report.lat:.6f}, {report.lng:.6f})",
        f"Ward/locality: {report.ward_label or 'unknown'}",
        f"Map: https://www.openstreetmap.org/?mlat={report.lat}&mlon={report.lng}#map=18/{report.lat}/{report.lng}",
        f"Citizens affected (reports merged): {affected}",
    ]
    if report.image:
        lines.append(f"Photo: {media_url(report.image)}")
    if report.transcript_en:
        lines.append(f"Citizen voice note (translated): {report.transcript_en}")
    if reason:
        lines.append(f"Routing reason: {reason}")
    lines += [
        "",
        "Please acknowledge or update the status here (no login needed):",
        f"{settings.PUBLIC_BASE_URL.rstrip('/')}/ack/{dispatch.ack_token}/",
        "",
        f"Public status page: {settings.FRONTEND_BASE_URL.rstrip('/')}/r/{report.ref_no}",
        "",
        "Sent by CivicPulse, an independent citizen platform. AI-generated severity is decision support and may be wrong.",
    ]
    return "\n".join(lines)


def _recipient_for(channel):
    """Returns (recipient, error)."""
    if settings.DISPATCH_MODE == "live":
        if not channel or channel.type != ContactChannel.EMAIL:
            return None, "no automated (email) channel"
        if not channel.verified_at:
            return None, "channel is not verified"
        return channel.address, None
    if not settings.SANDBOX_EMAIL:
        return None, "DISPATCH_MODE=sandbox but SANDBOX_EMAIL is not set"
    return settings.SANDBOX_EMAIL, None


def _send(dispatch, recipient):
    msg = EmailMessage(subject=dispatch.subject, body=dispatch.body, from_email=settings.DEFAULT_FROM_EMAIL,
                       to=[recipient], reply_to=[settings.DEFAULT_FROM_EMAIL])
    msg.send(fail_silently=False)


def dispatch_to_authority(report, authority, reason="", escalated_from=None, sleep=time.sleep):
    """Tries each channel of `authority` (retry with backoff). Returns the Dispatch record (sent or failed)."""
    channels = list(authority.channels.all()) or [None]
    last = None
    for channel in channels:
        recipient, err = _recipient_for(channel)
        d = Dispatch.objects.create(report=report, authority=authority, channel=channel, mode=settings.DISPATCH_MODE,
                                    recipient=recipient or "", escalated_from=escalated_from)
        d.subject = f"[CivicPulse {report.ref_no}] {report.severity_level.upper() or 'NEW'} - {CATEGORY_LABEL.get(report.category, report.category)} - {report.ward_label or report.address[:40]}"
        d.body = build_complaint(report, d, reason)
        d.save(update_fields=["subject", "body"])
        last = d
        if err:
            d.delivery_status, d.error = Dispatch.FAILED, err
            d.save(update_fields=["delivery_status", "error"])
            continue
        for attempt in range(1, MAX_ATTEMPTS + 1):
            d.attempts = attempt
            try:
                _send(d, recipient)
                d.delivery_status, d.error, d.sent_at = Dispatch.SENT, "", timezone.now()
                d.save(update_fields=["attempts", "delivery_status", "error", "sent_at"])
                return d
            except Exception as exc:  # noqa: BLE001
                d.error = f"{type(exc).__name__}: {exc}"
                log.warning("dispatch attempt %s failed: %s", attempt, exc)
                d.save(update_fields=["attempts", "error"])
                if attempt < MAX_ATTEMPTS:
                    sleep(2 ** attempt)
        d.delivery_status = Dispatch.FAILED
        d.save(update_fields=["delivery_status"])
    return last


def dispatch_with_fallback(report, authority, reason=""):
    """Dispatch to `authority`; on failure walk up the escalation parent chain (self-correction on failed dispatch)."""
    tried = []
    current = authority
    while current is not None and current.pk not in tried:
        tried.append(current.pk)
        d = dispatch_to_authority(report, current, reason)
        if d and d.delivery_status == Dispatch.SENT:
            note = f"Complaint emailed to {current.name}" + (f" (fallback after failure at {authority.name})" if current != authority else "")
            if d.mode == "sandbox":
                note += " [sandbox mode: delivered to the team test inbox]"
            report.authority = current
            report.save(update_fields=["authority", "updated_at"])
            report.set_status(Status.SENT, actor="system", note=note)
            return d
        report.set_status(report.status, actor="system",
                          note=f"Delivery to {current.name} failed: {d.error if d else 'no channel'}; trying escalation parent.", save=False)
        current = current.parent
    report.set_status(Status.DISPATCH_FAILED, actor="system", note="All delivery channels failed; queued for moderator.")
    return None
