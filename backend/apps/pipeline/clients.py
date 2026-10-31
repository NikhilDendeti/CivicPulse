"""Thin clients for external services. Each returns None / raises ServiceUnavailable on failure;
nothing here ever invents data. Callers record the failure and degrade honestly."""
import base64
import io
import logging
import os

import requests
from django.conf import settings
from PIL import Image, ImageOps

log = logging.getLogger(__name__)
HTTP_TIMEOUT = 15


class ServiceUnavailable(Exception):
    pass


# ---------------------------------------------------------------- OpenAI ----
def openai_client():
    if not settings.OPENAI_API_KEY:
        raise ServiceUnavailable("OPENAI_API_KEY is not configured")
    from openai import OpenAI

    return OpenAI(api_key=settings.OPENAI_API_KEY, timeout=45, max_retries=2)


def image_to_data_url(path, max_side=1024):
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def embed_text(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        res = openai_client().embeddings.create(model=settings.OPENAI_EMBED_MODEL, input=text[:4000])
        return res.data[0].embedding
    except Exception as exc:  # noqa: BLE001
        log.warning("embedding failed: %s", exc)
        return None


# ---------------------------------------------------------------- Sarvam ----
SARVAM_BASE = "https://api.sarvam.ai"
SARVAM_STT_MODEL = os.environ.get("SARVAM_STT_MODEL", "saarika:v2.5")
SARVAM_TRANSLATE_MODEL = os.environ.get("SARVAM_TRANSLATE_MODEL", "mayura:v1")


def sarvam_transcribe(path, lang_hint="unknown"):
    """Returns (transcript, detected_language_code). Raises ServiceUnavailable on failure."""
    if not settings.SARVAM_API_KEY:
        raise ServiceUnavailable("SARVAM_API_KEY is not configured")
    code = {"te": "te-IN", "en": "en-IN", "hi": "hi-IN"}.get(lang_hint, "unknown")
    name = os.path.basename(path)
    ctype = "audio/webm" if name.endswith("webm") else "audio/ogg" if name.endswith(("ogg", "opus")) \
        else "audio/mpeg" if name.endswith("mp3") else "audio/wav" if name.endswith("wav") else "application/octet-stream"
    try:
        with open(path, "rb") as fh:
            res = requests.post(
                f"{SARVAM_BASE}/speech-to-text",
                headers={"api-subscription-key": settings.SARVAM_API_KEY},
                files={"file": (name, fh, ctype)},
                data={"model": SARVAM_STT_MODEL, "language_code": code},
                timeout=60,
            )
        res.raise_for_status()
        body = res.json()
    except Exception as exc:  # noqa: BLE001
        raise ServiceUnavailable(f"Sarvam speech-to-text failed: {exc}") from exc
    return (body.get("transcript") or "").strip(), body.get("language_code") or code


def sarvam_translate_to_english(text, source_code):
    if not text:
        return ""
    if source_code.startswith("en"):
        return text
    if not settings.SARVAM_API_KEY:
        raise ServiceUnavailable("SARVAM_API_KEY is not configured")
    try:
        res = requests.post(
            f"{SARVAM_BASE}/translate",
            headers={"api-subscription-key": settings.SARVAM_API_KEY, "Content-Type": "application/json"},
            json={
                "input": text,
                "source_language_code": source_code if source_code != "unknown" else "auto",
                "target_language_code": "en-IN",
                "model": SARVAM_TRANSLATE_MODEL,
            },
            timeout=30,
        )
        res.raise_for_status()
        return (res.json().get("translated_text") or "").strip()
    except Exception as exc:  # noqa: BLE001
        raise ServiceUnavailable(f"Sarvam translation failed: {exc}") from exc


# ----------------------------------------------------------- OSM / weather --
def reverse_geocode(lat, lng):
    """Nominatim reverse geocode. Returns dict(address, locality) or None."""
    try:
        res = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"format": "jsonv2", "lat": lat, "lon": lng, "zoom": 18, "addressdetails": 1},
            headers={"User-Agent": settings.NOMINATIM_USER_AGENT},
            timeout=HTTP_TIMEOUT,
        )
        res.raise_for_status()
        body = res.json()
        addr = body.get("address", {})
        locality = addr.get("suburb") or addr.get("neighbourhood") or addr.get("city_district") or addr.get("village") or ""
        return {"address": body.get("display_name", ""), "locality": locality}
    except Exception as exc:  # noqa: BLE001
        log.warning("reverse geocode failed: %s", exc)
        return None


OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def _osm_headers():
    return {"User-Agent": settings.NOMINATIM_USER_AGENT}


def nearby_sensitive_sites(lat, lng, radius=200):
    """Schools / hospitals near the point via OSM Overpass. Returns list of {kind, name} or None on failure."""
    q = (f'[out:json][timeout:10];(nwr(around:{radius},{lat},{lng})["amenity"~"^(school|hospital|clinic|college|kindergarten)$"];);'
         "out tags 10;")
    try:
        res = requests.post(OVERPASS_URL, data={"data": q}, headers=_osm_headers(), timeout=HTTP_TIMEOUT)
        res.raise_for_status()
        out = []
        for el in res.json().get("elements", []):
            t = el.get("tags", {})
            out.append({"kind": t.get("amenity"), "name": t.get("name", "")})
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("overpass sites failed: %s", exc)
        return None


def road_class(lat, lng):
    q = f'[out:json][timeout:10];way(around:25,{lat},{lng})["highway"];out tags 5;'
    try:
        res = requests.post(OVERPASS_URL, data={"data": q}, headers=_osm_headers(), timeout=HTTP_TIMEOUT)
        res.raise_for_status()
        classes = [e.get("tags", {}).get("highway") for e in res.json().get("elements", [])]
        for c in ("motorway", "trunk", "primary", "secondary", "tertiary"):
            if c in classes:
                return c
        return classes[0] if classes else None
    except Exception as exc:  # noqa: BLE001
        log.warning("overpass road class failed: %s", exc)
        return None


def current_precipitation_mm(lat, lng):
    try:
        res = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lng, "current": "precipitation"},
            timeout=HTTP_TIMEOUT,
        )
        res.raise_for_status()
        return float(res.json().get("current", {}).get("precipitation", 0.0))
    except Exception as exc:  # noqa: BLE001
        log.warning("weather failed: %s", exc)
        return None
