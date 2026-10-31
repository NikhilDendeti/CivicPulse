"""Duplicate detection (FR-8): same category + within radius + (embedding similarity or near-identical image).
Precision-first: if neither signal is available, reports are NOT merged."""
import math

import imagehash
from django.conf import settings

from apps.authorities.geo import haversine_m
from apps.reports.models import IssueCluster, Report, Status


def cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def phash_distance(h1, h2):
    if not h1 or not h2:
        return None
    return imagehash.hex_to_hash(h1) - imagehash.hex_to_hash(h2)


def find_duplicate(report):
    """Returns (existing_report, similarity_note) or (None, None)."""
    qs = Report.objects.filter(category=report.category, status__in=Status.OPEN).exclude(pk=report.pk) \
        .exclude(status__in=[Status.MERGED, Status.NEEDS_INFO, Status.NEEDS_REVIEW, Status.SUBMITTED, Status.ANALYSING])
    best, best_note, best_score = None, None, -1.0
    for cand in qs:
        if haversine_m(report.lat, report.lng, cand.lat, cand.lng) > settings.DUPLICATE_RADIUS_M:
            continue
        sim = cosine(report.embedding, cand.embedding)
        dist = phash_distance(report.phash, cand.phash)
        same_image = dist is not None and dist <= 6
        if sim >= settings.DUPLICATE_SIMILARITY or same_image:
            score = max(sim, 1.0 if same_image else 0.0)
            if score > best_score:
                best, best_score = cand, score
                best_note = f"text similarity {sim:.2f}" + (f", image hash distance {dist}" if dist is not None else "")
    return best, best_note


def merge_into(report, existing, note):
    cluster = existing.cluster
    if cluster is None:
        cluster = IssueCluster.objects.create(category=existing.category, lat=existing.lat, lng=existing.lng,
                                              canonical=existing, affected_count=1)
        existing.cluster = cluster
        existing.save(update_fields=["cluster", "updated_at"])
    cluster.affected_count += 1
    cluster.save(update_fields=["affected_count"])
    report.cluster = cluster
    report.save(update_fields=["cluster", "updated_at"])
    report.set_status(Status.MERGED, actor="system",
                      note=f"Matched existing report {existing.ref_no} ({note}); now {cluster.affected_count} citizens affected.")
    return cluster
