from django.contrib import admin

from .models import Authority, ContactChannel, Ward


class ChannelInline(admin.TabularInline):
    model = ContactChannel
    extra = 0


@admin.register(Authority)
class AuthorityAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "source_url")
    inlines = [ChannelInline]


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "source_url")
    search_fields = ("name",)
