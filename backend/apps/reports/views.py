from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status as http
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.authorities.models import CATEGORIES, CATEGORY_KEYS
from apps.dispatch.services import dispatch_to_authority
from apps.pipeline import tasks

from . import media
from .models import ModerationAction, Report, Status
from .serializers import serialize_report

LEVEL_SCORE = {"low": 15, "medium": 42, "high": 66, "critical": 88}


def _token(request):
    return request.headers.get("X-Device-Token") or request.data.get("device_token") or request.query_params.get("device_token", "")


def _is_owner(request, report):
    t = _token(request)
    return bool(t) and bool(report.device_token) and t == report.device_token


def _bad(msg, code=http.HTTP_400_BAD_REQUEST):
    return Response({"error": msg}, status=code)


class MetaView(APIView):
    def get(self, request):
        return Response({
            "categories": [{"key": k, "label": v} for k, v in CATEGORIES if k != "other"],
            "dispatch_mode": settings.DISPATCH_MODE,
            "max_audio_seconds": settings.MAX_AUDIO_SECONDS,
            "confidence_threshold": settings.CONFIDENCE_THRESHOLD,
            "pilot_area": "Hyderabad",
        })


class ReportCreateView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "report_create"

    def post(self, request):
        d = request.data
        try:
            lat, lng = float(d.get("lat")), float(d.get("lng"))
        except (TypeError, ValueError):
            return _bad("A valid location (lat, lng) is required.")
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return _bad("Location is out of range.")
        if str(d.get("consent", "")).lower() not in ("1", "true", "yes", "on"):
            return _bad("Consent is required to submit a report.")
        token = _token(request)
        if not token or len(token) > 64:
            return _bad("A device token is required.")

        image, audio, video = request.FILES.get("image"), request.FILES.get("audio"), request.FILES.get("video")
        text = (d.get("text") or "").strip()[:1500]
        if not (image or audio or video or text):
            return _bad("Add a photo, video, voice note or a short description.")

        report = Report(device_token=token, consent=True, lat=lat, lng=lng, text=text,
                        lang=(d.get("lang") or "en")[:5], citizen_email=(d.get("email") or "")[:254])
        try:
            report.accuracy_m = float(d["accuracy"]) if d.get("accuracy") else None
        except ValueError:
            report.accuracy_m = None
        try:
            flags = []
            if image:
                content, report.phash, flags = media.process_image(image, lat, lng)
                report.image.save("photo.jpg", content, save=False)
            if audio:
                media.check_audio(audio)
                report.audio = audio
            if video:
                media.check_video(video)
                report.video = video
        except media.MediaError as exc:
            return _bad(str(exc))
        report.authenticity_flags = flags
        report.save()
        report.set_status(Status.SUBMITTED, actor="citizen", note="Report received.")
        tasks.enqueue(tasks.process_report, report.pk)
        return Response(serialize_report(request, report, owner=True), status=http.HTTP_201_CREATED)


class ReportDetailView(APIView):
    def get(self, request, ref):
        report = get_object_or_404(Report, ref_no=ref)
        return Response(serialize_report(request, report, owner=_is_owner(request, report)))


class ConfirmView(APIView):
    """Citizen reviews the AI result, optionally corrects it, and confirms (FR: see result before sending)."""

    def post(self, request, ref):
        report = get_object_or_404(Report, ref_no=ref)
        if not _is_owner(request, report):
            return _bad("Only the reporter can confirm this report.", http.HTTP_403_FORBIDDEN)
        if report.status not in (Status.ANALYSED, Status.NEEDS_INFO):
            return _bad(f"This report cannot be confirmed while it is '{report.status}'.", http.HTTP_409_CONFLICT)
        category, level = request.data.get("category"), request.data.get("severity_level")
        if category and category not in CATEGORY_KEYS:
            return _bad("Unknown category.")
        if level and level not in LEVEL_SCORE:
            return _bad("Unknown severity level.")
        if report.status != Status.ANALYSED and not category:
            return _bad("Please choose a category so this report can be routed.")
        for field, new in (("category", category), ("severity_level", level)):
            old = getattr(report, field)
            if new and new != old:
                ModerationAction.objects.create(report=report, field=field, old_value=old, new_value=new,
                                                reason="Citizen correction")
                setattr(report, field, new)
                if field == "severity_level":
                    report.severity_score = LEVEL_SCORE[new]
        if not report.severity_level:  # citizen resolved an uncertain report by choosing manually
            report.severity_level, report.severity_score = "medium", LEVEL_SCORE["medium"]
        if category and report.embedding is not None:
            report.embedding = None  # recompute for the corrected category
        report.save()
        report.set_status(Status.ANALYSED, actor="citizen", note="Citizen confirmed the report" +
                          (" with corrections." if category or level else "."))
        tasks.enqueue(tasks.finalize_report, report.pk)
        return Response(serialize_report(request, report, owner=True))


class AnswerView(APIView):
    def post(self, request, ref):
        report = get_object_or_404(Report, ref_no=ref)
        if not _is_owner(request, report):
            return _bad("Only the reporter can answer.", http.HTTP_403_FORBIDDEN)
        if report.status != Status.NEEDS_INFO:
            return _bad("No question is waiting for an answer.", http.HTTP_409_CONFLICT)
        answer = (request.data.get("answer") or "").strip()[:1000]
        if not answer:
            return _bad("Please type an answer.")
        report.citizen_answer = answer
        report.save(update_fields=["citizen_answer", "updated_at"])
        report.set_status(Status.SUBMITTED, actor="citizen", note="Citizen answered the clarifying question.")
        tasks.enqueue(tasks.process_report, report.pk)
        return Response(serialize_report(request, report, owner=True))


class ResolutionView(APIView):
    """FR-24: citizen confirms or disputes a resolution; a dispute reopens and re-sends the case."""

    def post(self, request, ref):
        report = get_object_or_404(Report, ref_no=ref)
        if not _is_owner(request, report):
            return _bad("Only the reporter can respond to a resolution.", http.HTTP_403_FORBIDDEN)
        if report.status != Status.RESOLVED:
            return _bad("This report is not marked resolved.", http.HTTP_409_CONFLICT)
        action = request.data.get("action")
        if action == "confirm":
            report.set_status(Status.RESOLVED, actor="citizen", note="Citizen confirmed the issue is fixed.")
        elif action == "dispute":
            note = (request.data.get("note") or "").strip()[:500]
            report.set_status(Status.DISPUTED, actor="citizen", note="Citizen disputes the resolution. " + note)
            report.set_status(Status.REOPENED, actor="system", note="Case reopened.")
            if report.authority:
                report.text = f"{report.text}\n[Reopened: {note}]".strip()
                report.save(update_fields=["text", "updated_at"])
                d = dispatch_to_authority(report, report.authority, reason="Citizen disputed the resolution; case reopened.")
                if d and d.delivery_status == "sent":
                    report.set_status(Status.SENT, actor="system", note=f"Reopened complaint re-sent to {report.authority.name}.")
        else:
            return _bad("action must be 'confirm' or 'dispute'.")
        return Response(serialize_report(request, report, owner=True))
