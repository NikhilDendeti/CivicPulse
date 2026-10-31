"""Routing agent (FR-10, FR-11, FR-12, FR-13): an LLM with tools chooses the authority and dispatches.
If the LLM is unavailable the deterministic top candidate is used and the reason says so."""
import json
import logging

from django.conf import settings

from apps.authorities.geo import authorities_for
from apps.authorities.models import Authority
from apps.dispatch.services import dispatch_with_fallback
from apps.reports.models import Report, Status

from . import clients

log = logging.getLogger(__name__)
MAX_STEPS = 6

SYSTEM = """You are the routing agent of a civic complaints platform in Hyderabad.
Given one report, pick the single authority responsible for its category and location, then send the complaint.
Use find_authorities first. Choose the authority whose categories and jurisdiction match; prefer the most specific
jurisdiction. Then call send_dispatch with a short reason (what rule or fact decided it) and your confidence 0-1.
If no authority fits or you are unsure (confidence < 0.5), call flag_for_moderator instead of guessing.
Never invent authorities; only use ids returned by find_authorities."""

TOOLS = [
    {"type": "function", "function": {
        "name": "find_authorities",
        "description": "List authorities that handle this report's category at its location, with their contact channels.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "send_dispatch",
        "description": "Generate the structured complaint and send it to the chosen authority.",
        "parameters": {"type": "object", "additionalProperties": False,
                       "required": ["authority_id", "reason", "confidence"],
                       "properties": {"authority_id": {"type": "integer"},
                                      "reason": {"type": "string"},
                                      "confidence": {"type": "number"}}}}},
    {"type": "function", "function": {
        "name": "flag_for_moderator",
        "description": "Stop and send this report to a human moderator.",
        "parameters": {"type": "object", "additionalProperties": False, "required": ["reason"],
                       "properties": {"reason": {"type": "string"}}}}},
]


def _candidates(report):
    return authorities_for(report.category, report.lat, report.lng)


def _describe(auth):
    return {"id": auth.pk, "name": auth.name, "categories": auth.categories,
            "scope": "specific area" if auth.jurisdiction else "whole pilot area",
            "channels": [{"type": c.type, "verified": bool(c.verified_at)} for c in auth.channels.all()]}


def _finish(report, authority, reason, confidence):
    report.authority = authority
    report.routing_reason = reason
    report.routing_confidence = confidence
    report.save(update_fields=["authority", "routing_reason", "routing_confidence", "updated_at"])
    report.set_status(Status.ROUTED, actor="routing-agent", note=f"Routed to {authority.name}. {reason}")
    dispatch_with_fallback(report, authority, reason)


def _flag(report, reason):
    report.routing_reason = reason
    report.save(update_fields=["routing_reason", "updated_at"])
    report.set_status(Status.NEEDS_REVIEW, actor="routing-agent", note=f"Needs human routing review: {reason}")


def _deterministic(report, why):
    cands = _candidates(report)
    if not cands:
        return _flag(report, f"No authority is registered for category '{report.category}' at this location. {why}")
    # Most specific first: a bounded jurisdiction, then a leaf authority (one that escalates to a parent).
    cands.sort(key=lambda a: (0 if a.jurisdiction else 1, 0 if a.parent_id else 1))
    a = cands[0]
    _finish(report, a, f"Rule-based: {a.name} handles '{report.category}' for this location. ({why})", 0.6)


def route_and_dispatch(report):
    if not _candidates(report):
        return _flag(report, f"No authority handles '{report.category}' at this location.")
    try:
        client = clients.openai_client()
    except clients.ServiceUnavailable as exc:
        return _deterministic(report, f"language model unavailable: {exc}")

    facts = {"ref": report.ref_no, "category": report.category, "severity": report.severity_level,
             "address": report.address, "ward": report.ward_label, "lat": report.lat, "lng": report.lng}
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": "Route this report: " + json.dumps(facts)}]
    seen_ids = set()
    try:
        for _ in range(MAX_STEPS):
            res = client.chat.completions.create(model=settings.OPENAI_AGENT_MODEL, messages=messages,
                                                 tools=TOOLS, tool_choice="auto", temperature=0)
            msg = res.choices[0].message
            if not msg.tool_calls:
                break
            messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
                {"id": t.id, "type": "function", "function": {"name": t.function.name, "arguments": t.function.arguments}}
                for t in msg.tool_calls]})
            for call in msg.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                if call.function.name == "find_authorities":
                    cands = _candidates(report)
                    seen_ids.update(a.pk for a in cands)
                    out = {"authorities": [_describe(a) for a in cands]}
                elif call.function.name == "flag_for_moderator":
                    return _flag(report, args.get("reason", "agent requested review"))
                elif call.function.name == "send_dispatch":
                    aid, conf = args.get("authority_id"), float(args.get("confidence", 0))
                    if aid not in seen_ids:
                        out = {"error": "unknown authority_id; call find_authorities and use a returned id"}
                    elif conf < 0.5:
                        return _flag(report, f"Agent confidence {conf:.2f}: {args.get('reason', '')}")
                    else:
                        return _finish(report, Authority.objects.get(pk=aid), args.get("reason", ""), conf)
                else:
                    out = {"error": "unknown tool"}
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(out)})
    except Exception as exc:  # noqa: BLE001
        log.warning("routing agent failed: %s", exc)
        return _deterministic(report, f"agent error: {type(exc).__name__}")
    return _deterministic(report, "agent did not complete a dispatch")
