from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from .forms import UserRegisterForm
from django.contrib.auth.views import LoginView
from .models import CCRForm, CCRSubmission, Course
from .ccr_forms import CCRSubmissionForm

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


def check_ccr_form_status():
    """
    Check if CCR forms are active
    """
    try:
        ccr_form_obj = CCRForm.objects.filter(name="CCR Form").first()
        if ccr_form_obj and ccr_form_obj.status == CCRForm.STATUS_ACTIVE:
            return True
        return False
    except Exception:
        return False


@login_required
def dashboard(request):
    role = getattr(request.user, "role", None)
    form_active = check_ccr_form_status()
    
    if role == "admin":
        template = "accounts/dashboard_admin.html"
    elif role == "course_collaborator":
        template = "accounts/dashboard_collaborator.html"
    else:
        template = "accounts/dashboard_faculty.html"
    
    context = {
        'form_active': form_active,
    }
    
    # Add context based on user role
    if role == 'faculty':
        assigned_courses = request.user.assigned_courses.all() if hasattr(request.user, 'assigned_courses') else []
        recent_submissions = CCRSubmission.objects.filter(
            faculty=request.user
        ).order_by('-submission_date')[:5] if hasattr(request.user, 'ccr_submissions') else []
        
        context.update({
            'assigned_courses': assigned_courses,
            'recent_submissions': recent_submissions,
        })
    
    return render(request, template, context)


@login_required
def ccr_form(request):
    # Check if CCR form is active
    try:
        ccr_form_obj = CCRForm.objects.filter(name="CCR Form").first()
        
        if not ccr_form_obj:
            messages.error(request, "CCR Form is not configured. Please contact administrator.")
            return redirect('dashboard')
            
        if ccr_form_obj.status != CCRForm.STATUS_ACTIVE:
            messages.error(request, "CCR Form is currently not available for submission.")
            return redirect('dashboard')
    except Exception as e:
        messages.error(request, "Error accessing CCR Form. Please try again later.")
        return redirect('dashboard')
    
    # Check if user is faculty
    if request.user.role != 'faculty':
        messages.error(request, "Only faculty members can submit CCR forms.")
        return redirect('dashboard')
    
    # Check if faculty has assigned courses
    if not request.user.assigned_courses.exists():
        messages.error(request, "You don't have any assigned courses to submit CCR forms for.")
        return redirect('dashboard')
    
    # Handle form submission
    if request.method == 'POST':
        form = CCRSubmissionForm(request.POST, faculty=request.user)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.faculty = request.user
            submission.ccr_form = ccr_form_obj
            
            # Check if already submitted for this course
            existing_submission = CCRSubmission.objects.filter(
                faculty=request.user, 
                course=submission.course,
                ccr_form=ccr_form_obj
            ).first()
            
            if existing_submission:
                messages.error(request, f"You have already submitted a CCR form for {submission.course.title}.")
                return render(request, 'accounts/ccr_form.html', {
                    'form': form,
                    'ccr_form': ccr_form_obj,
                    'form_active': True  # Form is active since we're in the form view
                })
            
            submission.save()
            messages.success(request, "CCR Form submitted successfully! You can submit another form or go back to dashboard.")
            # Stay on the same page to allow multiple submissions
            return redirect('ccr_form')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = CCRSubmissionForm(faculty=request.user)
    
    return render(request, 'accounts/ccr_form.html', {
        'form': form,
        'ccr_form': ccr_form_obj,
        'form_active': True  # Form is active since we're in the form view
    })


@login_required
def ccr_submissions(request):
    if request.user.role != 'faculty':
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    
    submissions = CCRSubmission.objects.filter(faculty=request.user).select_related('course').order_by('-submission_date')
    form_active = check_ccr_form_status()
    
    return render(request, 'accounts/ccr_submissions.html', {
        'submissions': submissions,
        'form_active': form_active
    })