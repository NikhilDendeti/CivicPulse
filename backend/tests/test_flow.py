from datetime import timedelta

import pytest
from django.core import mail
from django.test import Client
from django.utils import timezone

from apps.dispatch.models import Dispatch
from apps.pipeline import tasks
from apps.reports.models import Report, Status

from .conftest import make_jpeg

TOKEN = "device-abc"
HDR = {"HTTP_X_DEVICE_TOKEN": TOKEN}


def submit(client, lat=17.385, lng=78.4867, text="big pothole here", consent="true", token=TOKEN, image=True):
    data = {"lat": lat, "lng": lng, "text": text, "consent": consent, "device_token": token}
    if image:
        data["image"] = make_jpeg()
    return client.post("/api/reports/", data)


@pytest.mark.django_db
def test_requires_consent_and_evidence():
    c = Client()
    assert submit(c, consent="false").status_code == 400
    assert c.post("/api/reports/", {"lat": 17.3, "lng": 78.4, "consent": "true", "device_token": TOKEN}).status_code == 400


@pytest.mark.django_db
def test_full_flow_report_to_acknowledged(no_network, analysis_result, authorities):
    c = Client()
    res = submit(c)
    assert res.status_code == 201
    ref = res.json()["ref_no"]
    r = Report.objects.get(ref_no=ref)
    assert r.status == Status.ANALYSED
    assert r.category == "road_damage" and r.severity_level in ("medium", "high")
    assert r.ward_label == "Test Locality"
    assert "Exif" not in open(r.image.path, "rb").read(2000).decode("latin1")  # EXIF stripped

    # Only the owner can confirm.
    assert c.post(f"/api/reports/{ref}/confirm/", {}, content_type="application/json", **{"HTTP_X_DEVICE_TOKEN": "someone-else"}).status_code == 403
    out = c.post(f"/api/reports/{ref}/confirm/", {}, content_type="application/json", **HDR)
    assert out.status_code == 200
    r.refresh_from_db()
    assert r.status == Status.SENT
    assert r.authority.name == "Roads Dept"
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["team-inbox@example.test"]  # sandbox mode never mails the real department
    assert f"/ack/{Dispatch.objects.get().ack_token}/" in mail.outbox[0].body

    # Officer acknowledges and resolves through the tokenised page.
    token = Dispatch.objects.get().ack_token
    assert c.post(f"/ack/{token}/", {"action": "acknowledge"}).status_code == 200
    r.refresh_from_db()
    assert r.status == Status.ACKNOWLEDGED
    c.post(f"/ack/{token}/", {"action": "resolve", "note": "Filled"})
    r.refresh_from_db()
    assert r.status == Status.RESOLVED

    pub = c.get(f"/api/reports/{ref}/").json()
    assert pub["is_owner"] is False and "address" not in pub and "transcript" not in pub
    assert [e["status"] for e in pub["timeline"]][-3:] == ["sent", "acknowledged", "resolved"]

    # Citizen disputes -> reopened and re-sent.
    out = c.post(f"/api/reports/{ref}/resolution/", {"action": "dispute", "note": "still broken"}, content_type="application/json", **HDR)
    assert out.status_code == 200
    r.refresh_from_db()
    assert r.status == Status.SENT and len(mail.outbox) == 2


@pytest.mark.django_db
def test_low_confidence_asks_citizen_then_moderation(no_network, analysis_result, authorities):
    analysis_result.update(confidence=0.3, clarifying_question="Is that a pothole or a manhole?")
    c = Client()
    ref = submit(c).json()["ref_no"]
    r = Report.objects.get(ref_no=ref)
    assert r.status == Status.NEEDS_INFO
    assert c.get(f"/api/reports/{ref}/", **HDR).json()["clarifying_question"].startswith("Is that")
    # Still low after the answer -> human review rather than a guess.
    c.post(f"/api/reports/{ref}/answer/", {"answer": "not sure"}, content_type="application/json", **HDR)
    r.refresh_from_db()
    assert r.status == Status.NEEDS_REVIEW
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_irrelevant_goes_to_moderation(no_network, analysis_result, authorities):
    analysis_result.update(is_relevant=False)
    ref = submit(Client()).json()["ref_no"]
    assert Report.objects.get(ref_no=ref).status == Status.NEEDS_REVIEW


@pytest.mark.django_db
def test_ai_unavailable_does_not_guess(no_network, monkeypatch, authorities):
    from apps.pipeline import analysis, clients

    def boom(report):
        raise clients.ServiceUnavailable("OPENAI_API_KEY is not configured")

    monkeypatch.setattr(analysis, "analyse", boom)
    r = Report.objects.get(ref_no=submit(Client()).json()["ref_no"])
    assert r.status == Status.NEEDS_REVIEW and r.category == "" and "OPENAI" in r.ai_error


@pytest.mark.django_db
def test_duplicate_is_merged_not_dispatched_twice(no_network, analysis_result, authorities):
    c = Client()
    first = submit(c).json()["ref_no"]
    c.post(f"/api/reports/{first}/confirm/", {}, content_type="application/json", **HDR)
    second = submit(c, lat=17.38503, lng=78.48672, token="other-dev").json()["ref_no"]
    c.post(f"/api/reports/{second}/confirm/", {}, content_type="application/json", **{"HTTP_X_DEVICE_TOKEN": "other-dev"})
    r2 = Report.objects.get(ref_no=second)
    assert r2.status == Status.MERGED
    assert r2.cluster.affected_count == 2
    assert len(mail.outbox) == 1
    assert c.get(f"/api/reports/{second}/").json()["canonical_ref"] == first


@pytest.mark.django_db
def test_nearby_different_issue_not_merged(no_network, analysis_result, authorities):
    c = Client()
    first = submit(c, text="big pothole").json()["ref_no"]
    c.post(f"/api/reports/{first}/confirm/", {}, content_type="application/json", **HDR)
    analysis_result["description"] = "A cracked kerb"  # embedding differs (no 'pothole')
    second = submit(c, text="cracked kerb", lat=17.38503, lng=78.48672, token="o2", image=False).json()["ref_no"]
    # image=False => no phash; embeddings orthogonal => no merge
    c.post(f"/api/reports/{second}/confirm/", {}, content_type="application/json", **{"HTTP_X_DEVICE_TOKEN": "o2"})
    assert Report.objects.get(ref_no=second).status == Status.SENT


@pytest.mark.django_db
def test_failed_delivery_retries_then_falls_back_to_parent(no_network, analysis_result, authorities, monkeypatch):
    from apps.dispatch import services

    calls = []

    def flaky(dispatch, recipient):
        calls.append(dispatch.authority.slug)
        if dispatch.authority.slug == "roads":
            raise ConnectionError("smtp down")

    monkeypatch.setattr(services, "_send", flaky)
    monkeypatch.setattr(services.time, "sleep", lambda s: None)
    c = Client()
    ref = submit(c).json()["ref_no"]
    c.post(f"/api/reports/{ref}/confirm/", {}, content_type="application/json", **HDR)
    r = Report.objects.get(ref_no=ref)
    assert calls == ["roads", "roads", "roads", "parent"]
    assert r.status == Status.SENT and r.authority.slug == "parent"
    assert Dispatch.objects.filter(authority__slug="roads").get().delivery_status == "failed"


@pytest.mark.django_db
def test_all_channels_failing_is_reported_honestly(no_network, analysis_result, authorities, monkeypatch):
    from apps.dispatch import services

    monkeypatch.setattr(services, "_send", lambda d, r: (_ for _ in ()).throw(ConnectionError("down")))
    monkeypatch.setattr(services.time, "sleep", lambda s: None)
    c = Client()
    ref = submit(c).json()["ref_no"]
    c.post(f"/api/reports/{ref}/confirm/", {}, content_type="application/json", **HDR)
    assert Report.objects.get(ref_no=ref).status == Status.DISPATCH_FAILED


@pytest.mark.django_db
def test_live_mode_refuses_unverified_channel(no_network, analysis_result, authorities, settings):
    settings.DISPATCH_MODE = "live"
    c = Client()
    ref = submit(c).json()["ref_no"]
    c.post(f"/api/reports/{ref}/confirm/", {}, content_type="application/json", **HDR)
    assert len(mail.outbox) == 0  # nothing is mailed to an unverified address
    assert Report.objects.get(ref_no=ref).status == Status.DISPATCH_FAILED


@pytest.mark.django_db
def test_escalation_on_ack_timeout(no_network, analysis_result, authorities):
    c = Client()
    ref = submit(c).json()["ref_no"]
    c.post(f"/api/reports/{ref}/confirm/", {}, content_type="application/json", **HDR)
    assert tasks.escalate_overdue() == 0  # not overdue yet
    later = timezone.now() + timedelta(hours=49)
    assert tasks.escalate_overdue(now=later) == 1
    assert Dispatch.objects.count() == 2 and len(mail.outbox) == 2
    assert tasks.escalate_overdue(now=later) == 0  # only once


@pytest.mark.django_db
def test_dashboard_empty_state_and_metrics(no_network, analysis_result, authorities):
    c = Client()
    m = c.get("/api/metrics/?group=ward").json()
    assert m["rows"] == [] and m["totals"]["reports"] == 0
    assert c.get("/api/map/").json()["features"] == []
    ref = submit(c).json()["ref_no"]
    assert c.get("/api/metrics/").json()["totals"]["reports"] == 0  # unconfirmed reports are not public
    c.post(f"/api/reports/{ref}/confirm/", {}, content_type="application/json", **HDR)
    token = Dispatch.objects.get().ack_token
    c.post(f"/ack/{token}/", {"action": "acknowledge"})
    m = c.get("/api/metrics/?group=department").json()
    assert m["rows"][0]["name"] == "Roads Dept" and m["rows"][0]["acknowledged"] == 1
    assert m["rows"][0]["median_hours_to_acknowledge"] is not None
    csv = c.get("/api/export/reports.csv").content.decode()
    assert "device" not in csv and ref in csv
