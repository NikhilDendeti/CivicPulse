from django.contrib import admin

from .models import Dispatch


@admin.register(Dispatch)
class DispatchAdmin(admin.ModelAdmin):
    list_display = ("report", "authority", "recipient", "mode", "delivery_status", "attempts", "created_at")
    list_filter = ("delivery_status", "mode")
    readonly_fields = ("ack_token",)
