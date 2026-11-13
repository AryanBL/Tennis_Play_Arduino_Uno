from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/state/", views.state, name="state"),
    path("api/keyboard/", views.keyboard, name="keyboard"),
]
