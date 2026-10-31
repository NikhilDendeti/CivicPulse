from django.urls import path

from . import views

urlpatterns = [
    path("map/", views.MapView.as_view()),
    path("metrics/", views.MetricsView.as_view()),
    path("export/reports.csv", views.export_csv),
]
