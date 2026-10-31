"""Tokenised, login-free officer page: the department acknowledges / updates / resolves from the emailed link."""
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from apps.reports.models import Status
from apps.reports.media import MediaError, process_image

from .models import Dispatch

ACTIONS = {
    "acknowledge": (Status.ACKNOWLEDGED, "Acknowledged"),
    "in_progress": (Status.IN_PROGRESS, "Work in progress"),
    "resolve": (Status.RESOLVED, "Resolved"),
}
ALLOWED_FROM = {
    "acknowledge": {Status.SENT, Status.REOPENED, Status.DISPUTED},
    "in_progress": {Status.SENT, Status.ACKNOWLEDGED, Status.REOPENED},
    "resolve": {Status.SENT, Status.ACKNOWLEDGED, Status.IN_PROGRESS, Status.REOPENED},
}


def ack_page(request, token):
    dispatch = get_object_or_404(Dispatch.objects.select_related("report", "authority"), ack_token=token)
    report = dispatch.report
    message, error = "", ""
    if request.method == "POST":
        action = request.POST.get("action")
        if action not in ACTIONS:
            error = "Unknown action."
        elif report.status not in ALLOWED_FROM[action]:
            error = f"This case is currently '{report.status}', so that update is not available."
        else:
            note = request.POST.get("note", "").strip()[:500]
            proof = None
            if action == "resolve" and request.FILES.get("proof"):
                try:
                    proof, _, _ = process_image(request.FILES["proof"], report.lat, report.lng)
                except MediaError as exc:
                    error = str(exc)
            if not error:
                new_status, label = ACTIONS[action]
                ev = report.set_status(new_status, actor=f"officer:{dispatch.authority.name}",
                                       note=note or f"{label} by {dispatch.authority.name}.")
                if proof:
                    ev.proof.save("proof.jpg", proof, save=True)
                if action == "acknowledge" and not dispatch.acknowledged_at:
                    dispatch.acknowledged_at = timezone.now()
                    dispatch.save(update_fields=["acknowledged_at"])
                message = f"Thank you. Status updated to: {label}."
                report.refresh_from_db()
    return render(request, "dispatch/ack.html", {
        "report": report, "dispatch": dispatch, "message": message, "error": error,
        "events": report.events.all(),
        "can": {a: report.status in ALLOWED_FROM[a] for a in ACTIONS},
    })
