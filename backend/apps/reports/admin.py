from django.contrib import admin

from .models import IssueCluster, ModerationAction, Report, StatusEvent


class EventInline(admin.TabularInline):
    model = StatusEvent
    extra = 0
    readonly_fields = ("status", "actor", "note", "at")
    can_delete = False


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("ref_no", "category", "severity_level", "confidence", "status", "ward", "authority", "created_at")
    list_filter = ("status", "category", "severity_level", "ward")
    search_fields = ("ref_no", "address", "description")
    readonly_fields = ("ref_no", "embedding", "phash", "created_at")
    inlines = [EventInline]
    actions = ["rerun_analysis", "approve_and_route", "reject_reports"]

    @admin.action(description="Re-run AI analysis")
    def rerun_analysis(self, request, queryset):
        from apps.pipeline import tasks
        for r in queryset:
            r.set_status("submitted", actor="moderator", note="Moderator requested re-analysis.")
            tasks.enqueue(tasks.process_report, r.pk)

    @admin.action(description="Approve and route to the responsible authority")
    def approve_and_route(self, request, queryset):
        from apps.pipeline import tasks
        for r in queryset.exclude(category=""):
            if not r.severity_level:
                r.severity_level, r.severity_score = "medium", 42
                r.save(update_fields=["severity_level", "severity_score"])
            r.set_status("analysed", actor="moderator", note="Moderator approved the report for routing.")
            tasks.enqueue(tasks.finalize_report, r.pk)

    @admin.action(description="Reject (abusive / irrelevant)")
    def reject_reports(self, request, queryset):
        for r in queryset:
            r.set_status("rejected", actor="moderator", note="Rejected by a moderator.")

    def save_model(self, request, obj, form, change):
        # Moderator corrections are logged as feedback for evaluation (FR-17).
        if change:
            old = Report.objects.get(pk=obj.pk)
            for field in ("category", "severity_level", "authority_id", "status"):
                if getattr(old, field) != getattr(obj, field):
                    ModerationAction.objects.create(
                        report=obj, field=field, old_value=str(getattr(old, field)),
                        new_value=str(getattr(obj, field)), reason="Edited in admin", by=request.user,
                    )
        super().save_model(request, obj, form, change)


@admin.register(IssueCluster)
class ClusterAdmin(admin.ModelAdmin):
    list_display = ("id", "category", "affected_count", "lat", "lng")


@admin.register(ModerationAction)
class ModerationActionAdmin(admin.ModelAdmin):
    list_display = ("report", "field", "old_value", "new_value", "by", "at")
