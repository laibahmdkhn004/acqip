from django.contrib import admin # pyright: ignore[reportMissingModuleSource]
from django.conf import settings
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.contrib.staticfiles.views import serve as serve_static
from django.urls import path, include, re_path # pyright: ignore[reportMissingModuleSource]

urlpatterns = [
    path("admin/", admin.site.urls),
    # include accounts app at root so /, /login/, /register/, /dashboard/ work
    path("", include("accounts.urls")),
]

# App static files (accounts/static/...) — needed for local runserver.
# When DEBUG=True, Django's normal staticfiles URLs are enough.
# When DEBUG=False (common in .env), serve via finders with insecure=True
# so images like bg-login.jpg still load during local development.
if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
else:
    urlpatterns += [
        re_path(r"^static/(?P<path>.*)$", serve_static, {"insecure": True}),
    ]
