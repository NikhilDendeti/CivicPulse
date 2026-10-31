import csv

from django.core.management.base import BaseCommand

from apps.reports.models import ModerationAction, Report, Status

ORDER = ["low", "medium", "high", "critical"]


class Command(BaseCommand):
    help = ("Compare system output with human labels. CSV columns: ref_no,category,severity_level,authority_slug "
            "(authority_slug optional). Prints accuracy with the sample size; nothing is estimated or invented.")

    def add_arguments(self, parser):
        parser.add_argument("labels_csv")

    def handle(self, *args, **o):
        rows = list(csv.DictReader(open(o["labels_csv"], encoding="utf-8")))
        n = cat_ok = sev_ok = sev_adj = rt_n = rt_ok = 0
        missing = []
        for row in rows:
            r = Report.objects.filter(ref_no=row["ref_no"].strip()).first()
            if not r:
                missing.append(row["ref_no"])
                continue
            # Use the AI's first output, not a citizen/moderator correction: undo logged corrections.
            cat, sev = r.category, r.severity_level
            for m in r.moderation_actions.order_by("at"):
                if m.field == "category" and m.old_value:
                    cat = m.old_value if cat == m.new_value else cat
                if m.field == "severity_level" and m.old_value:
                    sev = m.old_value if sev == m.new_value else sev
            n += 1
            cat_ok += cat == row["category"].strip()
            if sev in ORDER and row["severity_level"].strip() in ORDER:
                d = abs(ORDER.index(sev) - ORDER.index(row["severity_level"].strip()))
                sev_ok += d == 0
                sev_adj += d <= 1
            slug = (row.get("authority_slug") or "").strip()
            if slug:
                rt_n += 1
                rt_ok += bool(r.authority and r.authority.slug == slug)
        total = Report.objects.count()
        review = Report.objects.filter(status=Status.NEEDS_REVIEW).count()
        pct = lambda a, b: f"{a}/{b} = {a / b:.0%}" if b else "n/a"  # noqa: E731
        self.stdout.write(f"Labelled reports matched: {n} (missing refs: {missing or 'none'})")
        self.stdout.write(f"Category accuracy:        {pct(cat_ok, n)}")
        self.stdout.write(f"Severity exact match:     {pct(sev_ok, n)}")
        self.stdout.write(f"Severity within 1 level:  {pct(sev_adj, n)}")
        self.stdout.write(f"Routing accuracy:         {pct(rt_ok, rt_n)}")
        self.stdout.write(f"Sent to human review:     {pct(review, total)} of all reports")
        self.stdout.write(f"Citizen/moderator corrections logged: {ModerationAction.objects.count()}")
        self.stdout.write("Duplicate precision: review merged reports manually (status=merged) and count correct merges.")
