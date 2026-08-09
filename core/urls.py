from __future__ import annotations

from django.urls import path

from . import views


urlpatterns = [
    path("index.html", views.index, name="index"),
    path("dashboard.html", views.dashboard, name="dashboard"),
    path("search.html", views.search, name="search"),
    path("upload.html", views.upload_page, name="upload_page"),
    path("profile.html", views.profile, name="profile"),
    path("auth.html", views.auth, name="auth"),
    path("file-view.html", views.file_view, name="file_view"),
    path("upload", views.upload_files, name="upload_api"),
    path("upload/", views.upload_files, name="upload_api_slash"),
]
