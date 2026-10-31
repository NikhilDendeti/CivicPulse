import io
import os

import pytest
from PIL import Image

os.environ["PIPELINE_SYNC"] = "1"


@pytest.fixture(autouse=True)
def _env(settings, tmp_path):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DISPATCH_MODE = "sandbox"
    settings.SANDBOX_EMAIL = "team-inbox@example.test"
    settings.CELERY_BROKER_URL = ""
    settings.OPENAI_API_KEY = ""  # force deterministic routing unless a test patches the agent
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.PUBLIC_BASE_URL = "http://testserver"


@pytest.fixture
def no_network(monkeypatch):
    """Stub every outbound lookup so tests are hermetic."""
    from apps.pipeline import clients

    monkeypatch.setattr(clients, "reverse_geocode", lambda lat, lng: {"address": "Test Road, Hyderabad", "locality": "Test Locality"})
    monkeypatch.setattr(clients, "nearby_sensitive_sites", lambda *a, **k: [])
    monkeypatch.setattr(clients, "road_class", lambda *a, **k: None)
    monkeypatch.setattr(clients, "current_precipitation_mm", lambda *a, **k: 0.0)
    monkeypatch.setattr(clients, "embed_text", lambda text: [1.0, 0.0, 0.0] if "pothole" in (text or "") else [0.0, 1.0, 0.0])


@pytest.fixture
def analysis_result(monkeypatch):
    from apps.pipeline import analysis

    state = {"category": "road_damage", "severity_base": 60, "confidence": 0.9, "is_relevant": True,
             "rationale": "Large pothole on a road.", "factors": ["deep hole"], "description": "A deep pothole in the road.",
             "clarifying_question": ""}
    monkeypatch.setattr(analysis, "analyse", lambda report: dict(state))
    return state


@pytest.fixture
def authorities(db):
    from apps.authorities.models import Authority, ContactChannel

    parent = Authority.objects.create(name="Parent Corp", slug="parent", categories=["road_damage"])
    child = Authority.objects.create(name="Roads Dept", slug="roads", categories=["road_damage"], parent=parent)
    ContactChannel.objects.create(authority=child, address="roads@example.test")
    ContactChannel.objects.create(authority=parent, address="parent@example.test")
    return parent, child


def make_jpeg(color=(200, 30, 30), size=(64, 64)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    buf.seek(0)
    buf.name = "p.jpg"
    return buf
