from django.contrib import admin 
from django.urls import path, include 

urlpatterns = [
    path("admin/", admin.site.urls),
    # include accounts app at root so /, /login/, /register/, /dashboard/ work
    path("", include("accounts.urls")),
]
