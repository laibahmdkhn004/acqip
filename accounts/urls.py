from django.urls import path
from . import views

urlpatterns = [
    # root route
    path("", views.home, name="home"),

    # authentication
    path("register/", views.register, name="register"),
    path("login/", views.CustomLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),  

    # dashboard (role-based)
    path("dashboard/", views.dashboard, name="dashboard"),
]
