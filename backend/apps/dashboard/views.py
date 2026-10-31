"""Public accountability dashboard (FR-18..FR-22). Reads live data only; empty database -> empty results."""
import csv
import statistics
from datetime import timedelta

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authorities.models import CATEGORIES
from apps.reports.models import Report, Status

CATEGORY_LABEL = dict(CATEGORIES)
# Reports shown publicly: moderated/accepted, not rejected, not awaiting review.
PUBLIC_EXCLUDE = [Status.SUBMITTED, Status.ANALYSING, Status.NEEDS_INFO, Status.NEEDS_REVIEW, Status.ANALYSED, Status.REJECTED]


def public_reports():
    return Report.objects.exclude(status__in=PUBLIC_EXCLUDE).exclude(category="")


def _first_time(report, statuses):
    for e in report.events.all():
        if e.status in statuses:
            return e.at
    return None


def _median_hours(values):
    return round(statistics.median(values), 2) if values else None


class MapView(APIView):
    def get(self, request):
        qs = public_reports().select_related("cluster")
        for key, field in (("category", "category"), ("severity", "severity_level"), ("status", "status"), ("ward", "ward_label")):
            v = request.query_params.get(key)
            if v:
                qs = qs.filter(**{field: v})
        features = []
        for r in qs[:1000]:
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(r.lng, 3), round(r.lat, 3)]},  # coarse public location
                "properties": {"ref_no": r.ref_no, "category": r.category, "category_label": CATEGORY_LABEL.get(r.category, ""),
                               "severity": r.severity_level, "status": r.status, "ward": r.ward_label,
                               "affected": r.cluster.affected_count if r.cluster else 1,
                               "created_at": r.created_at},
            })
        return Response({"type": "FeatureCollection", "features": features})


class MetricsView(APIView):
    """Aggregates by ward or by department, with plain-language definitions (FR-20, FR-22)."""

    DEFINITIONS = {
        "volume": "Number of public reports (duplicates counted once per citizen report).",
        "median_hours_to_acknowledge": "Median hours from the complaint being sent to the department acknowledging it. Only reports acknowledged so far.",
        "median_hours_to_resolve": "Median hours from the complaint being sent to the department marking it resolved. Only reports resolved so far.",
        "reopen_rate": "Share of resolved or reopened reports that the reporting citizen disputed.",
        "aging_backlog": "Open reports sent more than 7 days ago with no resolution.",
        "note": "A department's figures reflect only reports submitted through CivicPulse, depend on the department receiving the email, and are not a performance ranking.",
    }

    def get(self, request):
        group = request.query_params.get("group", "ward")
        key = (lambda r: r.ward_label or "Unknown area") if group == "ward" else (lambda r: r.authority.name if r.authority else "Not yet routed")
        now = timezone.now()
        buckets = {}
        for r in public_reports().select_related("authority").prefetch_related("events"):
            buckets.setdefault(key(r), []).append(r)
        rows = []
        for name, reports in sorted(buckets.items()):
            ack_h, res_h, reopened, resolved_or_reopened, backlog = [], [], 0, 0, 0
            for r in reports:
                sent = _first_time(r, {Status.SENT})
                ack = _first_time(r, {Status.ACKNOWLEDGED, Status.IN_PROGRESS, Status.RESOLVED})
                res = _first_time(r, {Status.RESOLVED})
                if sent and ack:
                    ack_h.append((ack - sent).total_seconds() / 3600)
                if sent and res:
                    res_h.append((res - sent).total_seconds() / 3600)
                if res or r.status in (Status.REOPENED, Status.DISPUTED):
                    resolved_or_reopened += 1
                if any(e.status == Status.DISPUTED for e in r.events.all()):
                    reopened += 1
                if r.status in Status.OPEN and sent and now - sent > timedelta(days=7):
                    backlog += 1
            rows.append({
                "name": name,
                "volume": len(reports),
                "sent": sum(1 for r in reports if _first_time(r, {Status.SENT})),
                "acknowledged": len(ack_h),
                "resolved": len(res_h),
                "median_hours_to_acknowledge": _median_hours(ack_h),
                "median_hours_to_resolve": _median_hours(res_h),
                "reopen_rate": round(reopened / resolved_or_reopened, 3) if resolved_or_reopened else None,
                "aging_backlog": backlog,
            })
        totals = public_reports()
        return Response({
            "group": group,
            "rows": rows,
            "totals": {"reports": totals.count(), "open": totals.filter(status__in=Status.OPEN).count(),
                       "resolved": totals.filter(status=Status.RESOLVED).count()},
            "definitions": self.DEFINITIONS,
        })


def export_csv(request):
    """FR-21: anonymised open-data export. No device tokens, contact details, free text, media or exact coordinates."""
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="civicpulse-reports.csv"'
    w = csv.writer(resp)
    w.writerow(["ref_no", "created_at", "category", "severity_level", "status", "ward", "authority",
                "lat_3dp", "lng_3dp", "affected_count", "hours_to_acknowledge", "hours_to_resolve"])
    for r in public_reports().select_related("authority", "cluster").prefetch_related("events"):
        sent = _first_time(r, {Status.SENT})
        ack = _first_time(r, {Status.ACKNOWLEDGED, Status.IN_PROGRESS, Status.RESOLVED})
        res = _first_time(r, {Status.RESOLVED})
        h = lambda a, b: round((b - a).total_seconds() / 3600, 2) if a and b else ""  # noqa: E731
        w.writerow([r.ref_no, r.created_at.isoformat(), r.category, r.severity_level, r.status, r.ward_label,
                    r.authority.name if r.authority else "", round(r.lat, 3), round(r.lng, 3),
                    r.cluster.affected_count if r.cluster else 1, h(sent, ack), h(sent, res)])
    return resp
