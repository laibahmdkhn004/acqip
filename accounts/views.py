from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.urls import reverse, reverse_lazy
from django import forms
from .forms import UserRegisterForm, UserPasswordResetForm, UserSetPasswordForm
from django.contrib.auth.views import (
    LoginView,
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from .models import Course, DynamicForm, FormQuestion, DynamicFormSubmission, CourseFaculty, FormAnswer, CourseOutline, User, Department
from django.db.models import Q, Count
import json
from .api_views import get_active_role, set_active_role, ACTIVE_ROLE_SESSION_KEY


ROLE_DISPLAY_MAP = {
    'Faculty': User.ROLE_FACULTY,
    'Lab Instructor': User.ROLE_LAB_INSTRUCTOR,
    'CRC': User.ROLE_CRC_MEMBER,
    'Admin': User.ROLE_ADMIN,
}

ROLE_LABELS = dict(User.ROLE_CHOICES)


def role_switcher_context(request):
    """Context for multi-role switcher UI."""
    if not request.user.is_authenticated:
        return {}
    roles = sorted(request.user.get_roles())
    active_role = get_active_role(request)
    return {
        'user_roles': roles,
        'user_roles_display': [
            {'code': code, 'label': ROLE_LABELS.get(code, code)}
            for code in roles
        ],
        'active_role': active_role,
        'active_role_label': ROLE_LABELS.get(active_role, active_role),
        'has_multiple_roles': len(roles) > 1,
    }

def landing_page(request):
    """Landing page for role selection"""
    return render(request, "accounts/landing.html")


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['role_choices'] = User.ROLE_CHOICES
        return context

    def form_valid(self, form):
        """Check that the user has the role from the URL/login card."""
        response = super().form_valid(form)

        requested_role = self.request.POST.get('role') or self.request.GET.get('role')
        if requested_role:
            internal_role = ROLE_DISPLAY_MAP.get(requested_role)

            if internal_role and not self.request.user.has_role(internal_role):
                from django.contrib.auth import logout
                logout(self.request)
                form.add_error(
                    None,
                    f"This login page is for {requested_role} only. "
                    f"You are not assigned that role.",
                )
                return self.form_invalid(form)

            if internal_role:
                set_active_role(self.request, internal_role)

        elif self.request.user.is_authenticated:
            # No login card role: use primary role
            set_active_role(self.request, self.request.user.role)

        return response


class CustomPasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/password_reset_email.txt"
    subject_template_name = "accounts/password_reset_subject.txt"
    form_class = UserPasswordResetForm
    success_url = reverse_lazy("password_reset_done")

    def form_valid(self, form):
        try:
            opts = {
                "use_https": self.request.is_secure(),
                "token_generator": self.token_generator,
                "from_email": self.from_email,
                "email_template_name": self.email_template_name,
                "subject_template_name": self.subject_template_name,
                "request": self.request,
                "html_email_template_name": self.html_email_template_name,
                "extra_email_context": self.extra_email_context,
            }
            form.save(**opts)
        except forms.ValidationError as validation_error:
            form.add_error(None, validation_error)
            return self.form_invalid(form)
        except Exception:
            form.add_error(
                None,
                "Unable to send the password reset email. Please try again later.",
            )
            return self.form_invalid(form)
        return super(PasswordResetView, self).form_valid(form)


class CustomPasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    form_class = UserSetPasswordForm
    success_url = reverse_lazy("password_reset_complete")


class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


@require_http_methods(["GET"])
def logout_view(request):
    if ACTIVE_ROLE_SESSION_KEY in request.session:
        del request.session[ACTIVE_ROLE_SESSION_KEY]
    logout(request)
    return redirect("login")


@login_required
def dynamic_form(request):
    if not request.user.has_role(User.ROLE_FACULTY, User.ROLE_LAB_INSTRUCTOR):
        messages.error(request, "Only faculty members and lab instructors can submit forms.")
        return redirect('dashboard')
    
    # Get form_id from URL if specified
    form_id = request.GET.get('form_id')
    
    # Check UNIVERSAL form availability (CCR/CRR/LRR)
    ccr_forms = DynamicForm.objects.filter(
        status=DynamicForm.STATUS_ACTIVE,
        form_type='ccr'
    ).order_by('-created_at')
    
    crr_forms = DynamicForm.objects.filter(
        status=DynamicForm.STATUS_ACTIVE,
        form_type='crr'
    ).order_by('-created_at')

    lrr_forms = DynamicForm.objects.filter(
        status=DynamicForm.STATUS_ACTIVE,
        form_type='lrr'
    ).order_by('-created_at')
    
    # Check if user is coordinator for ANY course
    is_coordinator_for_any = CourseFaculty.objects.filter(
        faculty=request.user,
        is_coordinator=True
    ).exists()
    
    # Get assigned courses
    assigned_courses = CourseFaculty.objects.filter(
        faculty=request.user
    ).select_related('course', 'course__department').prefetch_related('sections')
    
    courses_data = []
    for assignment in assigned_courses:
        courses_data.append({
            'id': assignment.course.id,
            'title': assignment.course.title,
            'code': assignment.course.code,
            'department': assignment.course.department.name if assignment.course.department else '',
            'is_coordinator': assignment.is_coordinator,
            'section': assignment.section_display(),
            'sections': [
                {'id': s.id, 'code': s.code, 'name': s.name}
                for s in assignment.sections.all()
            ],
        })
    
    # Check form type from URL
    active_role = get_active_role(request) or request.user.role
    default_form_type = 'lrr' if active_role == User.ROLE_LAB_INSTRUCTOR else 'crr'
    form_type = request.GET.get('form_type', default_form_type)
    course_id = request.GET.get('course_id')
    
    # If course_id is provided in URL, pre-select it
    selected_course = None
    if course_id:
        selected_course = next((c for c in courses_data if str(c['id']) == str(course_id)), None)
    
    # If form_id is provided, get the specific form
    selected_form = None
    if form_id:
        try:
            selected_form = DynamicForm.objects.get(id=form_id)
            form_type = selected_form.form_type
        except DynamicForm.DoesNotExist:
            pass

    can_faculty = request.user.has_role(User.ROLE_FACULTY)
    can_lrr = request.user.has_role(User.ROLE_LAB_INSTRUCTOR)
    
    context = {
        'assigned_courses': courses_data,
        'selected_course': selected_course,
        'selected_form': selected_form,
        'form_type': form_type,
        'form_id': form_id,
        'ccr_forms': list(ccr_forms.values('id', 'name', 'description')),
        'crr_forms': list(crr_forms.values('id', 'name', 'description')),
        'lrr_forms': list(lrr_forms.values('id', 'name', 'description')),
        'ccr_active': ccr_forms.exists() and can_faculty,
        'crr_active': crr_forms.exists() and can_faculty,
        'lrr_active': lrr_forms.exists() and can_lrr,
        'is_coordinator_for_any': is_coordinator_for_any,
        'is_lab_instructor': (
            active_role == User.ROLE_LAB_INSTRUCTOR and not can_faculty
        ) or (active_role == User.ROLE_LAB_INSTRUCTOR),
        'user_role': active_role,
        'user_department': request.user.department
    }
    context.update(role_switcher_context(request))
    # Show LRR button whenever user has lab instructor role
    if can_lrr and can_faculty:
        context['is_lab_instructor'] = False
    return render(request, 'accounts/dynamic_form.html', context)


@login_required
def dashboard(request):
    role = get_active_role(request)
    if not role:
        messages.error(request, "Access denied.")
        return redirect('landing')

    # Ensure session has an active role
    set_active_role(request, role)
    
    if role == User.ROLE_ADMIN:
        context = {
            'total_faculty': User.objects.filter(
                Q(role=User.ROLE_FACULTY) | Q(roles__code=User.ROLE_FACULTY)
            ).distinct().count(),
            'total_courses': Course.objects.count(),
            'total_departments': Department.objects.count(),
            'total_submissions': DynamicFormSubmission.objects.filter(status='submitted').count(),
        }
        context.update(role_switcher_context(request))
        return render(request, "accounts/dashboard_admin.html", context)
        
    elif role == User.ROLE_CRC_MEMBER:
        return crc_dashboard(request)

    elif role in (User.ROLE_FACULTY, User.ROLE_LAB_INSTRUCTOR):
        return faculty_dashboard(request)
        
    else:
        messages.error(request, "Access denied.")
        return redirect('landing')


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def switch_active_role(request):
    """Switch the active dashboard role for multi-role users."""
    role_code = request.POST.get('role') or ''
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        role_code = payload.get('role') or role_code
    except (TypeError, ValueError, json.JSONDecodeError):
        pass

    if not set_active_role(request, role_code):
        return JsonResponse({'error': 'You do not have that role'}, status=403)

    return JsonResponse({
        'success': True,
        'active_role': role_code,
        'redirect_url': reverse('dashboard'),
    })


@login_required
def ccr_submissions(request):
    if not request.user.has_role(
        User.ROLE_FACULTY,
        User.ROLE_LAB_INSTRUCTOR,
        User.ROLE_ADMIN,
        User.ROLE_CRC_MEMBER,
    ):
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    
    # For faculty/lab instructors, only show their own submissions
    if request.user.has_role(User.ROLE_FACULTY, User.ROLE_LAB_INSTRUCTOR) and not request.user.has_role(
        User.ROLE_ADMIN, User.ROLE_CRC_MEMBER
    ):
        submissions = DynamicFormSubmission.objects.filter(
            faculty=request.user,
            dynamic_form__form_type__in=['ccr', 'crr', 'lrr']  # Only universal forms
        ).select_related('course', 'dynamic_form').order_by('-submission_date')
    else:  # admin or crc_member can see all
        submissions = DynamicFormSubmission.objects.filter(
            dynamic_form__form_type__in=['ccr', 'crr', 'lrr']  # Only universal forms
        ).select_related(
            'faculty', 'course', 'dynamic_form'
        ).order_by('-submission_date')
    
    # Format submissions for template
    submissions_with_counts = []
    for submission in submissions:
        answer_count = FormAnswer.objects.filter(submission=submission).count()
        submissions_with_counts.append({
            'submission': submission,
            'answer_count': answer_count
        })
    
    # Check form availability (only universal forms)
    ccr_active = DynamicForm.objects.filter(
        status=DynamicForm.STATUS_ACTIVE,
        form_type='ccr'
    ).exists()
    
    crr_active = DynamicForm.objects.filter(
        status=DynamicForm.STATUS_ACTIVE,
        form_type='crr'
    ).exists()

    lrr_active = DynamicForm.objects.filter(
        status=DynamicForm.STATUS_ACTIVE,
        form_type='lrr'
    ).exists()
    
    return render(request, 'accounts/ccr_submissions.html', {
        'submissions': submissions_with_counts,
        'total_count': submissions.count(),
        'ccr_count': submissions.filter(dynamic_form__form_type='ccr').count(),
        'crr_count': submissions.filter(dynamic_form__form_type='crr').count(),
        'lrr_count': submissions.filter(dynamic_form__form_type='lrr').count(),
        'ccr_active': ccr_active,
        'crr_active': crr_active,
        'lrr_active': lrr_active,
        'user_role': request.user.role
    })

@login_required
def crc_dashboard(request):
    """CRC Member Dashboard"""
    if not request.user.has_role(User.ROLE_CRC_MEMBER, User.ROLE_ADMIN):
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    
    # Get statistics for CRC dashboard
    total_faculty = User.objects.filter(
        Q(role=User.ROLE_FACULTY) | Q(roles__code=User.ROLE_FACULTY)
    ).distinct().count()
    total_courses = Course.objects.count()
    
    # Count pending outlines (submitted but not approved)
    pending_outlines = CourseOutline.objects.filter(
        status__in=['submitted', 'revision_requested']
    ).count()
    
    total_submissions = DynamicFormSubmission.objects.filter(status='submitted').count()
    
    # Get active forms (only universal CCR/CRR)
    active_forms = list(DynamicForm.objects.filter(
        status='active',
        form_type__in=['ccr', 'crr', 'lrr']
    ).values('name', 'form_type'))
    
    # Get recent submissions (last 10)
    recent_submissions = DynamicFormSubmission.objects.filter(
        status='submitted',
        dynamic_form__form_type__in=['ccr', 'crr', 'lrr']  # Only universal forms
    ).select_related('faculty', 'course', 'dynamic_form').order_by('-submission_date')[:10]
    
    # Format recent submissions
    formatted_submissions = []
    for sub in recent_submissions:
        formatted_submissions.append({
            'id': sub.id,
            'faculty': {
                'id': sub.faculty.id,
                'username': sub.faculty.username,
                'email': sub.faculty.email
            },
            'course': {
                'id': sub.course.id,
                'title': sub.course.title,
                'code': sub.course.code
            },
            'form': {
                'id': sub.dynamic_form.id,
                'name': sub.dynamic_form.name,
                'form_type': sub.dynamic_form.form_type
            },
            'status': sub.status,
            'submission_date': sub.submission_date.strftime('%Y-%m-%d %H:%M') if sub.submission_date else '',
            'is_coordinator': sub.is_coordinator,
            'section': sub.section
        })
    
    # Get pending course outlines (last 5)
    pending_course_outlines = CourseOutline.objects.filter(
        status__in=['submitted', 'revision_requested']
    ).select_related('course', 'faculty').order_by('-submitted_at')[:5]
    
    # Format pending outlines
    formatted_outlines = []
    for outline in pending_course_outlines:
        formatted_outlines.append({
            'id': outline.id,
            'course': {
                'id': outline.course.id,
                'title': outline.course.title,
                'code': outline.course.code
            },
            'faculty': {
                'id': outline.faculty.id,
                'username': outline.faculty.username
            },
            'version': outline.version,
            'title': outline.title,
            'status': outline.status,
            'submitted_at': outline.submitted_at.strftime('%Y-%m-%d %H:%M') if outline.submitted_at else '',
            'notes': outline.notes
        })
    
    # Get faculty list for filtering
    faculty_list = User.objects.filter(role__in=[User.ROLE_FACULTY, User.ROLE_LAB_INSTRUCTOR]).values('id', 'username', 'email', 'role')[:20]
    
    # Get course list for filtering
    course_list = Course.objects.all().values('id', 'code', 'title')[:10]
    
    context = {
        'total_faculty': total_faculty,
        'total_courses': total_courses,
        'pending_outlines': pending_outlines,
        'total_submissions': total_submissions,
        'active_forms': active_forms,
        'recent_submissions': formatted_submissions,
        'pending_course_outlines': formatted_outlines,
        'user_role': get_active_role(request) or request.user.role,
        'faculty_list': list(faculty_list),
        'course_list': list(course_list),
    }
    context.update(role_switcher_context(request))
    
    return render(request, 'accounts/dashboard_crc.html', context)

@login_required
def faculty_dashboard(request):
    if not request.user.has_role(User.ROLE_FACULTY, User.ROLE_LAB_INSTRUCTOR):
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    
    active_role = get_active_role(request) or request.user.role
    can_faculty_forms = request.user.has_role(User.ROLE_FACULTY)
    can_lrr = request.user.has_role(User.ROLE_LAB_INSTRUCTOR)

    # Active role drives which form set is emphasized in the UI
    if active_role == User.ROLE_LAB_INSTRUCTOR:
        is_lab_instructor = True
        ccr_active = False
        crr_active = False
        lrr_active = can_lrr and DynamicForm.objects.filter(
            status=DynamicForm.STATUS_ACTIVE, form_type='lrr'
        ).exists()
    else:
        is_lab_instructor = False
        ccr_active = can_faculty_forms and DynamicForm.objects.filter(
            status=DynamicForm.STATUS_ACTIVE, form_type='ccr'
        ).exists()
        crr_active = can_faculty_forms and DynamicForm.objects.filter(
            status=DynamicForm.STATUS_ACTIVE, form_type='crr'
        ).exists()
        # Dual-role users also see LRR when on faculty dashboard
        lrr_active = can_lrr and DynamicForm.objects.filter(
            status=DynamicForm.STATUS_ACTIVE, form_type='lrr'
        ).exists()
    
    # Check if user is coordinator for ANY course (for CCR access)
    is_coordinator_for_any = CourseFaculty.objects.filter(
        faculty=request.user,
        is_coordinator=True
    ).exists()
    
    # Get assigned courses
    course_assignments = CourseFaculty.objects.filter(
        faculty=request.user
    ).select_related('course', 'course__department')
    
    assigned_courses = []
    for assignment in course_assignments:
        assigned_courses.append({
            'id': assignment.course.id,
            'title': assignment.course.title,
            'code': assignment.course.code,
            'description': assignment.course.description,
            'credits': assignment.course.credits,
            'department': assignment.course.department.name if assignment.course.department else '',
            'is_coordinator': assignment.is_coordinator,
            'section': assignment.section_display()
        })
    
    # Get recent form submissions (only for universal forms)
    recent_submissions = DynamicFormSubmission.objects.filter(
        faculty=request.user,
        dynamic_form__form_type__in=['ccr', 'crr', 'lrr']
    ).select_related('course', 'dynamic_form').order_by('-submission_date')[:5]
    
    # Format recent submissions
    formatted_submissions = []
    for sub in recent_submissions:
        formatted_submissions.append({
            'id': sub.id,
            'course': {
                'id': sub.course.id,
                'title': sub.course.title,
                'code': sub.course.code
            },
            'dynamic_form': {
                'id': sub.dynamic_form.id,
                'name': sub.dynamic_form.name,
                'form_type': sub.dynamic_form.form_type
            },
            'status': sub.status,
            'submission_date': sub.submission_date.strftime('%Y-%m-%d') if sub.submission_date else None,
            'is_coordinator': sub.is_coordinator,
            'section': sub.section
        })
    
    context = {
        'assigned_courses': assigned_courses,
        'recent_submissions': formatted_submissions,
        'total_submissions': DynamicFormSubmission.objects.filter(faculty=request.user).count(),
        'ccr_active': ccr_active,
        'crr_active': crr_active,
        'lrr_active': lrr_active,
        'is_coordinator_for_any': is_coordinator_for_any,
        'is_lab_instructor': is_lab_instructor,
        'user_role': active_role,
        'user_department': request.user.department,
        'user_designation': request.user.designation,
    }
    context.update(role_switcher_context(request))
    
    return render(request, 'accounts/dashboard_faculty.html', context)

@login_required
def course_outline_view(request):
    if not request.user.has_role(User.ROLE_FACULTY, User.ROLE_ADMIN, User.ROLE_CRC_MEMBER):
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    
    if request.user.has_role(User.ROLE_FACULTY) and not request.user.has_role(User.ROLE_ADMIN, User.ROLE_CRC_MEMBER):
        # Get courses where user is coordinator
        coordinator_courses = CourseFaculty.objects.filter(
            faculty=request.user,
            is_coordinator=True
        ).select_related('course', 'course__department')
        
        # Get existing outlines
        outlines = CourseOutline.objects.filter(
            faculty=request.user
        ).select_related('course').order_by('-created_at')
        
        return render(request, 'accounts/course_outline.html', {
            'coordinator_courses': coordinator_courses,
            'outlines': outlines
        })
    
    return render(request, 'accounts/course_outline.html')

@login_required
def course_outline_editor(request):
    """Standalone course outline editor (faculty coordinators only). CRC uses the in-dashboard editor."""
    if not request.user.has_role(User.ROLE_FACULTY):
        messages.error(request, "Access denied.")
        return redirect("dashboard")

    course_id = request.GET.get("course_id")
    outline_id = request.GET.get("outline_id")

    if not course_id and not outline_id:
        messages.error(request, "Course ID or Outline ID is required.")
        return redirect("faculty_dashboard")

    try:
        course = None
        existing_outline = None

        if outline_id:
            existing_outline = CourseOutline.objects.get(
                id=outline_id, faculty=request.user
            )
            course = existing_outline.course
            CourseFaculty.objects.get(
                faculty=request.user,
                course=course,
                is_coordinator=True,
            )
        else:
            CourseFaculty.objects.get(
                faculty=request.user,
                course_id=course_id,
                is_coordinator=True,
            )
            course = Course.objects.get(id=course_id)
            existing_outline = (
                CourseOutline.objects.filter(
                    course_id=course_id,
                    faculty=request.user,
                )
                .order_by("-version")
                .first()
            )

        context = {
            "course": {
                "id": course.id,
                "title": course.title,
                "code": course.code,
                "credits": course.credits,
                "department": course.department.name if course.department else "",
            },
            "existing_outline": existing_outline,
            "is_coordinator": True,
            "is_crc_member": False,
            "faculty_name": request.user.get_full_name() or request.user.username,
            "dashboard_home_url": reverse("faculty_dashboard"),
        }

        return render(request, "accounts/course_outline_editor.html", context)

    except CourseFaculty.DoesNotExist:
        messages.error(request, "You are not the coordinator for this course.")
        return redirect("faculty_dashboard")
    except (Course.DoesNotExist, CourseOutline.DoesNotExist):
        messages.error(request, "Course or outline not found.")
        return redirect("faculty_dashboard")
    except Exception as exc:
        messages.error(request, f"Error: {str(exc)}")
        return redirect("faculty_dashboard")