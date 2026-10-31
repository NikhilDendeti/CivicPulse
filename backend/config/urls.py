from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.reports.urls")),
    path("api/", include("apps.dashboard.urls")),
    path("", include("apps.dispatch.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
