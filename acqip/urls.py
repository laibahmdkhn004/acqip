from django.contrib import admin # pyright: ignore[reportMissingModuleSource]
from django.urls import path, include # pyright: ignore[reportMissingModuleSource]

urlpatterns = [
    path("admin/", admin.site.urls),
    # include accounts app at root so /, /login/, /register/, /dashboard/ work
    path("", include("accounts.urls")),
]
