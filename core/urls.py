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
    path("post-login/", views.post_login_sync, name="post_login_sync"),
    path("upload", views.upload_files, name="upload_api"),
    path("upload/", views.upload_files, name="upload_api_slash"),
    path("add-link", views.add_link, name="add_link_api"),
    path("add-link/", views.add_link, name="add_link_api_slash"),
    path("files", views.list_uploaded_files, name="uploaded_files_api"),
    path("files/", views.list_uploaded_files, name="uploaded_files_api_slash"),
    path("search-query", views.smart_search, name="smart_search_api"),
    path("search-query/", views.smart_search, name="smart_search_api_slash"),
    path("files/<str:file_id>/update", views.update_file_metadata, name="update_file_metadata_api"),
    path("files/<str:file_id>/status", views.file_status, name="file_status_api"),
]
