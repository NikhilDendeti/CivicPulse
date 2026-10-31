from django.urls import path

from . import views

urlpatterns = [
    path("ack/<str:token>/", views.ack_page, name="ack"),
]
