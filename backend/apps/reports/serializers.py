from apps.authorities.models import CATEGORIES
from apps.dispatch.models import Dispatch

CATEGORY_LABEL = dict(CATEGORIES)
HIDDEN_MEDIA_STATUSES = {"submitted", "analysing", "needs_info", "needs_review", "analysed", "rejected"}
ACTOR_LABEL = {"system": "System", "ai": "AI analysis", "routing-agent": "Routing agent", "citizen": "Citizen",
               "moderator": "Moderator"}


def _abs(request, f):
    return request.build_absolute_uri(f.url) if f else None


def actor_label(actor):
    if actor.startswith("officer:"):
        return actor.split(":", 1)[1] + " (department)"
    return ACTOR_LABEL.get(actor, actor)


def timeline(request, report):
    return [{"status": e.status, "actor": actor_label(e.actor), "note": e.note, "at": e.at,
             "proof_url": _abs(request, e.proof)} for e in report.events.all()]


def serialize_report(request, report, owner=False):
    """Public representation. Exact address, transcript and citizen contact are owner-only."""
    cluster = report.cluster
    canonical = cluster.canonical if cluster and cluster.canonical_id != report.pk else None
    data = {
        "ref_no": report.ref_no,
        "status": report.status,
        "category": report.category,
        "category_label": CATEGORY_LABEL.get(report.category, ""),
        "severity_level": report.severity_level,
        "severity_score": report.severity_score,
        "confidence": report.confidence,
        "rationale": report.rationale,
        "description": report.description,
        "factors": report.factors,
        "ward": report.ward_label,
        "lat": round(report.lat, 3) if not owner else report.lat,
        "lng": round(report.lng, 3) if not owner else report.lng,
        # Unreviewed or rejected evidence is only visible to its owner (abuse protection).
        "image_url": _abs(request, report.image) if owner or report.status not in HIDDEN_MEDIA_STATUSES else None,
        "routing_reason": report.routing_reason,
        "routing_confidence": report.routing_confidence,
        "authority": report.authority.name if report.authority else None,
        "affected_count": cluster.affected_count if cluster else 1,
        "canonical_ref": canonical.ref_no if canonical else None,
        "created_at": report.created_at,
        "timeline": timeline(request, report),
        "delivery": [{"authority": d.authority.name, "status": d.delivery_status, "mode": d.mode,
                      "sent_at": d.sent_at} for d in report.dispatches.select_related("authority")],
        "is_owner": owner,
    }
    if owner:
        data.update({
            "address": report.address,
            "clarifying_question": report.clarifying_question if report.status == "needs_info" else "",
            "transcript": report.transcript_en or report.transcript_orig,
            "text": report.text,
            "ai_error": report.ai_error,
            "authenticity_flags": report.authenticity_flags,
        })
    return data
