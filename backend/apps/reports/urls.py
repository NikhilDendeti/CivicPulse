from django.urls import path

from . import views

urlpatterns = [
    path("meta/", views.MetaView.as_view()),
    path("reports/", views.ReportCreateView.as_view()),
    path("reports/<str:ref>/", views.ReportDetailView.as_view()),
    path("reports/<str:ref>/confirm/", views.ConfirmView.as_view()),
    path("reports/<str:ref>/answer/", views.AnswerView.as_view()),
    path("reports/<str:ref>/resolution/", views.ResolutionView.as_view()),
]
