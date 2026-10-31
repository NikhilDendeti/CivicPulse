import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.authorities.models import Authority, ContactChannel


class Command(BaseCommand):
    help = ("Load the authority directory from a JSON file. A channel is only marked verified when the file entry "
            "has a non-empty 'verification_note' (record how you verified it, e.g. 'test email replied 2026-10-31').")

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=str(Path(__file__).resolve().parents[3].parent / "data" / "authorities.json"))

    def handle(self, *args, **o):
        with open(o["path"], encoding="utf-8") as fh:
            entries = json.load(fh)["authorities"]
        by_slug = {}
        for e in entries:
            a, _ = Authority.objects.update_or_create(
                slug=e["slug"],
                defaults={"name": e["name"], "categories": e["categories"], "source_url": e.get("source_url", ""),
                          "notes": e.get("notes", "")},
            )
            by_slug[e["slug"]] = a
            for ch in e.get("channels", []):
                verified = bool(ch.get("verification_note"))
                ContactChannel.objects.update_or_create(
                    authority=a, address=ch["address"],
                    defaults={"type": ch.get("type", "email"), "priority": ch.get("priority", 1),
                              "verification_note": ch.get("verification_note", ""),
                              "verified_at": timezone.now() if verified else None},
                )
        for e in entries:  # second pass: escalation parents
            if e.get("parent"):
                a = by_slug[e["slug"]]
                a.parent = by_slug[e["parent"]]
                a.save(update_fields=["parent"])
        self.stdout.write(self.style.SUCCESS(f"Loaded {len(entries)} authorities"))
