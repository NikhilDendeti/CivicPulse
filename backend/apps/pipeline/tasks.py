"""The per-report agent workflow:
analyse -> confidence gate (ask citizen / moderation) -> [citizen confirms] -> duplicate check -> route -> dispatch
-> wait for acknowledgement -> escalate on timeout. Runs on Celery when a broker is configured, else in a thread."""
import logging
import threading
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from apps.authorities.geo import find_ward, haversine_m
from apps.dispatch.models import Dispatch
from apps.dispatch.services import dispatch_to_authority
from apps.reports.models import Report, Status

from . import analysis, clients, duplicates, routing, severity

log = logging.getLogger(__name__)


# ------------------------------------------------------------ execution ----
def enqueue(task, report_id):
    """Run `task` (a shared_task) via Celery if configured, synchronously if PIPELINE_SYNC, else in a thread."""
    import os

    if settings.CELERY_BROKER_URL:
        task.delay(report_id)
    elif os.environ.get("PIPELINE_SYNC") == "1":
        task(report_id)
    else:
        def runner():
            close_old_connections()
            try:
                task(report_id)
            finally:
                close_old_connections()
        threading.Thread(target=runner, daemon=True).start()


# --------------------------------------------------------------- steps ----
def _ensure_location(report):
    if not report.address:
        geo = clients.reverse_geocode(report.lat, report.lng)
        if geo:
            report.address = geo["address"][:500]
            report.ward_label = geo["locality"][:200]
    ward = find_ward(report.lat, report.lng)
    if ward:
        report.ward, report.ward_label = ward, ward.name
    report.save(update_fields=["address", "ward", "ward_label", "updated_at"])


def _ensure_transcript(report):
    if report.audio and not report.transcript_orig:
        try:
            text, code = clients.sarvam_transcribe(report.audio.path, report.lang)
            report.transcript_orig = text
            report.transcript_en = clients.sarvam_translate_to_english(text, code) if text else ""
            if not text:
                report.ai_error = (report.ai_error + " Voice note contained no recognisable speech.").strip()
        except clients.ServiceUnavailable as exc:
            report.ai_error = (report.ai_error + f" {exc}").strip()
        report.save(update_fields=["transcript_orig", "transcript_en", "ai_error", "updated_at"])


def _check_reuse(report):
    flags = list(report.authenticity_flags)
    if report.phash:
        for other in Report.objects.exclude(pk=report.pk).exclude(phash="").filter(created_at__lt=report.created_at):
            d = duplicates.phash_distance(report.phash, other.phash)
            far = haversine_m(report.lat, report.lng, other.lat, other.lng) > 200
            if d is not None and d <= 3 and (far or other.device_token != report.device_token):
                if far:
                    flags.append(f"image closely matches {other.ref_no} reported at a different location")
                    break
    return flags


@shared_task
def process_report(report_id):
    report = Report.objects.get(pk=report_id)
    report.set_status(Status.ANALYSING, note="Analysing evidence")
    _ensure_location(report)
    _ensure_transcript(report)

    try:
        result = analysis.analyse(report)
    except clients.ServiceUnavailable as exc:
        report.ai_error = (report.ai_error + f" {exc}").strip()
        report.save(update_fields=["ai_error", "updated_at"])
        report.set_status(Status.NEEDS_REVIEW, actor="system",
                          note="Automatic analysis was unavailable, so this report was sent to a human moderator instead of guessing.")
        return

    score, level, notes = severity.apply_context(result["category"], result["severity_base"], report.lat, report.lng)
    report.category = result["category"]
    report.severity_score, report.severity_level = score, level
    report.confidence = result["confidence"]
    report.description = result["description"]
    report.rationale = result["rationale"] + (" " + " ".join(f"({f})" for f in result["factors"][:3]) if result["factors"] else "")
    report.factors = notes
    report.clarifying_question = result["clarifying_question"] if result["confidence"] < settings.CONFIDENCE_THRESHOLD else ""
    report.embedding = clients.embed_text(f"{result['category']}. {result['description']} {report.text} {report.transcript_en}")
    report.authenticity_flags = _check_reuse(report)
    report.save()

    if report.authenticity_flags:
        report.set_status(Status.NEEDS_REVIEW, actor="system",
                          note="Authenticity check flagged this report: " + "; ".join(report.authenticity_flags))
    elif not result["is_relevant"]:
        report.set_status(Status.NEEDS_REVIEW, actor="ai",
                          note="The evidence does not appear to show a civic issue; sent to a moderator.")
    elif result["confidence"] < settings.CONFIDENCE_THRESHOLD:
        if report.citizen_answer or not report.clarifying_question:
            report.set_status(Status.NEEDS_REVIEW, actor="ai", note="Confidence is still low after clarification; sent to a moderator.")
        else:
            report.set_status(Status.NEEDS_INFO, actor="ai", note="Low confidence; asked the citizen a clarifying question.")
    else:
        report.set_status(Status.ANALYSED, actor="ai",
                          note=f"Classified as {report.category}, severity {level} ({score}/100), confidence {report.confidence:.0%}.")


@shared_task
def finalize_report(report_id):
    """After the citizen confirms (or a moderator approves): dedupe, then route and dispatch."""
    report = Report.objects.get(pk=report_id)
    if report.status in (Status.SENT, Status.ROUTED, Status.MERGED, Status.RESOLVED, Status.ACKNOWLEDGED, Status.IN_PROGRESS):
        return
    if not report.category:
        report.set_status(Status.NEEDS_REVIEW, actor="system", note="No category assigned.")
        return
    if report.embedding is None:
        report.embedding = clients.embed_text(f"{report.category}. {report.description} {report.text} {report.transcript_en}")
        report.save(update_fields=["embedding", "updated_at"])
    existing, note = duplicates.find_duplicate(report)
    if existing:
        duplicates.merge_into(report, existing, note)
        return
    routing.route_and_dispatch(report)


@shared_task
def escalate_overdue_task(_=None):
    return escalate_overdue()


def escalate_overdue(now=None):
    """FR-13: escalate to the parent authority when acknowledgement is overdue."""
    now = now or timezone.now()
    count = 0
    pending = Dispatch.objects.filter(delivery_status=Dispatch.SENT, acknowledged_at__isnull=True,
                                      report__status=Status.SENT, escalations__isnull=True)
    for d in pending.select_related("report", "authority"):
        hours = settings.CRITICAL_ACK_WINDOW_HOURS if d.report.severity_level == "critical" else settings.ACK_WINDOW_HOURS
        if d.sent_at and now - d.sent_at < timedelta(hours=hours):
            continue
        parent = d.authority.parent
        if not parent:
            continue
        reason = f"Escalated: not acknowledged by {d.authority.name} within {hours:g} h."
        new = dispatch_to_authority(d.report, parent, reason=reason, escalated_from=d)
        d.report.set_status(Status.SENT, actor="system",
                            note=f"{reason} " + (f"Complaint sent to {parent.name}." if new.delivery_status == Dispatch.SENT
                                                else f"Delivery to {parent.name} failed: {new.error}"))
        count += 1
    return count
