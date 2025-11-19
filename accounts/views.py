from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from .forms import UserRegisterForm
from django.contrib.auth.views import LoginView

def home(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("login")


def register(request):
    if request.method == "POST":
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Account created. Please sign in.")
            return redirect("login")
    else:
        form = UserRegisterForm()
    return render(request, "accounts/register.html", {"form": form})


class CustomLoginView(LoginView):
    template_name = "accounts/login.html"


@require_http_methods(["GET"])
def logout_view(request):
    """
    Accept GET for the navbar link, log out the user and redirect to login page.
    """
    logout(request)
    return redirect("login")


@login_required
def dashboard(request):
    role = getattr(request.user, "role", None)
    if role == "admin":
        template = "accounts/dashboard_admin.html"
    elif role == "course_collaborator":
        template = "accounts/dashboard_collaborator.html"
    else:
        template = "accounts/dashboard_faculty.html"
    return render(request, template)
