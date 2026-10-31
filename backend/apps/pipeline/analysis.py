"""Multimodal classification + severity (FR-5, FR-6, FR-9)."""
import json
import logging

from django.conf import settings

from apps.authorities.models import CATEGORY_KEYS

from . import clients

log = logging.getLogger(__name__)

PROMPT_VERSION = "analysis-v1"

SYSTEM_PROMPT = """You triage civic-infrastructure complaints in Hyderabad, India for a municipal accountability platform.
You receive a citizen's photo (optional), their text and a voice-note transcript translated to English (optional).
Decide:
- category: one of road_damage, water_leak, garbage, streetlight, drainage, other.
  (road_damage = potholes/cracked roads/broken bridge or railing; water_leak = drinking-water pipe leak or burst;
   garbage = uncollected or burning waste; streetlight = non-working lights; drainage = blocked drains, sewage or stormwater overflow.)
- is_relevant: false if the photo is clearly not a civic issue (selfie, indoor, meme, screenshot) or no issue is described at all.
- severity_base: integer 0-100 for physical danger and public impact from the evidence ALONE
  (0-29 cosmetic/minor, 30-54 inconvenient, 55-77 hazardous, 78-100 imminent danger: structural failure, deep open hole on a busy road, live wires, major flooding).
- confidence: 0-1, how sure you are of category AND severity given the evidence. Be honest; blurry, dark, ambiguous or conflicting evidence means low confidence.
- rationale: 1-2 plain sentences a citizen can understand explaining the category and severity.
- factors: short list of the specific visible/stated facts that drove severity.
- description: one neutral factual sentence describing the issue (no blame, no names, no faces or number plates).
- clarifying_question: if confidence is below 0.6, one short question to the citizen that would resolve the uncertainty; otherwise an empty string.
Never invent details that are not in the evidence."""

SCHEMA = {
    "name": "civic_analysis",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["category", "is_relevant", "severity_base", "confidence", "rationale",
                     "factors", "description", "clarifying_question"],
        "properties": {
            "category": {"type": "string", "enum": CATEGORY_KEYS},
            "is_relevant": {"type": "boolean"},
            "severity_base": {"type": "integer", "minimum": 0, "maximum": 100},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string"},
            "factors": {"type": "array", "items": {"type": "string"}},
            "description": {"type": "string"},
            "clarifying_question": {"type": "string"},
        },
    },
}


def validate(result):
    """Defensive validation in addition to strict JSON schema; raises ValueError."""
    if result.get("category") not in CATEGORY_KEYS:
        raise ValueError("bad category")
    for k in ("severity_base",):
        result[k] = max(0, min(100, int(result[k])))
    result["confidence"] = max(0.0, min(1.0, float(result["confidence"])))
    result["factors"] = [str(f) for f in result.get("factors", [])][:8]
    return result


def analyse(report):
    """Run the vision model. Returns a validated dict. Raises clients.ServiceUnavailable on failure."""
    client = clients.openai_client()
    parts = []
    text_bits = []
    if report.text:
        text_bits.append(f"Citizen text: {report.text}")
    if report.transcript_en:
        text_bits.append(f"Voice note (translated to English): {report.transcript_en}")
    if report.citizen_answer:
        text_bits.append(f"Citizen's answer to a clarifying question: {report.citizen_answer}")
    parts.append({"type": "text", "text": "\n".join(text_bits) or "No text or voice note provided."})
    if report.image:
        parts.append({"type": "image_url", "image_url": {"url": clients.image_to_data_url(report.image.path)}})
    last_err = None
    for _ in range(2):  # one retry on malformed output
        try:
            res = client.chat.completions.create(
                model=settings.OPENAI_VISION_MODEL,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": parts}],
                response_format={"type": "json_schema", "json_schema": SCHEMA},
                temperature=0.2,
            )
            return validate(json.loads(res.choices[0].message.content))
        except clients.ServiceUnavailable:
            raise
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            last_err = exc
        except Exception as exc:  # noqa: BLE001
            raise clients.ServiceUnavailable(f"OpenAI analysis failed: {exc}") from exc
    raise clients.ServiceUnavailable(f"Model returned invalid output: {last_err}")
