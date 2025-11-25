from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from .models import Course, Form, User, Department, CCRForm, CCRSubmission
from django.contrib.auth.decorators import login_required, user_passes_test

def is_admin(user):
    return user.is_authenticated and user.role == User.ROLE_ADMIN

# Department API Views
@login_required
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def api_departments(request):
    departments = list(Department.objects.values('id', 'name', 'code', 'description'))
    return JsonResponse(departments, safe=False)

@login_required
@user_passes_test(is_admin)
@csrf_exempt
@require_http_methods(["POST"])
def api_departments_create(request):
    try:
        data = json.loads(request.body)
        department = Department.objects.create(
            name=data.get('name'),
            code=data.get('code'),
            description=data.get('description', '')
        )
        return JsonResponse({
            'id': department.id,
            'name': department.name,
            'code': department.code,
            'description': department.description
        }, status=201)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

# Department Detail with Courses and Faculty
@login_required
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def api_department_detail(request, department_id):
    try:
        department = Department.objects.get(id=department_id)
        
        # Get courses in this department with faculty info
        courses = Course.objects.filter(department=department).values(
            'id', 'title', 'code', 'description', 'credits'
        )
        
        # Add faculty information to each course
        courses_list = []
        for course in courses:
            course_data = dict(course)
            # Get faculty assigned to this course
            faculty_users = User.objects.filter(assigned_courses=course['id']).values('id', 'username', 'email')
            course_data['faculty'] = list(faculty_users)
            courses_list.append(course_data)
        
        return JsonResponse({
            'department': {
                'id': department.id,
                'name': department.name,
                'code': department.code,
                'description': department.description
            },
            'courses': courses_list,
            'total_courses': len(courses_list),
            'total_faculty': User.objects.filter(assigned_courses__department=department, role='faculty').distinct().count()
        })
    except Department.DoesNotExist:
        return JsonResponse({'error': 'Department not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

# Course API Views
@login_required
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def api_courses(request):
    courses = list(Course.objects.values('id', 'title', 'code', 'description', 'department_id', 'credits'))
    return JsonResponse(courses, safe=False)

@login_required
@user_passes_test(is_admin)
@csrf_exempt
@require_http_methods(["POST"])
def api_courses_create(request):
    try:
        data = json.loads(request.body)
        department = Department.objects.get(id=data.get('department_id'))
        course = Course.objects.create(
            title=data.get('title'),
            code=data.get('code'),
            description=data.get('description', ''),
            department=department,
            credits=data.get('credits', 3)
        )
        
        # Assign faculty if provided
        faculty_ids = data.get('faculty_ids', [])
        if faculty_ids:
            faculty_members = User.objects.filter(id__in=faculty_ids, role=User.ROLE_FACULTY)
            course.faculty.set(faculty_members)
        
        return JsonResponse({
            'id': course.id,
            'title': course.title,
            'code': course.code,
            'description': course.description,
            'department_id': course.department.id,
            'credits': course.credits
        }, status=201)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin)
@csrf_exempt
@require_http_methods(["PUT"])
def api_course_update(request, course_id):
    try:
        data = json.loads(request.body)
        course = Course.objects.get(id=course_id)
        course.title = data.get('title', course.title)
        course.code = data.get('code', course.code)
        course.description = data.get('description', course.description)
        course.credits = data.get('credits', course.credits)
        
        if 'department_id' in data:
            department = Department.objects.get(id=data['department_id'])
            course.department = department
        
        course.save()
        
        # Update faculty assignments
        if 'faculty_ids' in data:
            faculty_members = User.objects.filter(id__in=data['faculty_ids'], role=User.ROLE_FACULTY)
            course.faculty.set(faculty_members)
        
        return JsonResponse({
            'id': course.id,
            'title': course.title,
            'code': course.code,
            'description': course.description,
            'department_id': course.department.id,
            'credits': course.credits
        })
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin)
@csrf_exempt
@require_http_methods(["DELETE"])
def api_course_delete(request, course_id):
    try:
        course = Course.objects.get(id=course_id)
        course.delete()
        return JsonResponse({'message': 'Course deleted successfully'})
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)

# Faculty Assignment API
@login_required
@user_passes_test(is_admin)
@csrf_exempt
@require_http_methods(["POST"])
def api_assign_courses_to_faculty(request, user_id):
    try:
        data = json.loads(request.body)
        faculty_member = User.objects.get(id=user_id, role=User.ROLE_FACULTY)
        course_ids = data.get('course_ids', [])
        
        courses = Course.objects.filter(id__in=course_ids)
        faculty_member.assigned_courses.set(courses)
        
        return JsonResponse({
            'message': f'Successfully assigned {courses.count()} courses to {faculty_member.username}'
        })
    except User.DoesNotExist:
        return JsonResponse({'error': 'Faculty member not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

# Faculty Dashboard API
@login_required
def api_faculty_courses(request):
    if request.user.role != User.ROLE_FACULTY:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    courses = list(request.user.assigned_courses.values(
        'id', 'title', 'code', 'description', 'credits', 'department__name'
    ))
    return JsonResponse(courses, safe=False)

# Form API Views
@login_required
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def api_forms(request):
    forms = list(Form.objects.values('id', 'name', 'description'))
    return JsonResponse(forms, safe=False)

@login_required
@user_passes_test(is_admin)
@csrf_exempt
@require_http_methods(["POST"])
def api_forms_create(request):
    try:
        data = json.loads(request.body)
        form = Form.objects.create(
            name=data.get('name'),
            description=data.get('description', '')
        )
        return JsonResponse({
            'id': form.id,
            'name': form.name,
            'description': form.description
        }, status=201)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin)
@csrf_exempt
@require_http_methods(["PUT"])
def api_form_update(request, form_id):
    try:
        data = json.loads(request.body)
        form = Form.objects.get(id=form_id)
        form.name = data.get('name', form.name)
        form.description = data.get('description', form.description)
        form.save()
        return JsonResponse({
            'id': form.id,
            'name': form.name,
            'description': form.description
        })
    except Form.DoesNotExist:
        return JsonResponse({'error': 'Form not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin)
@csrf_exempt
@require_http_methods(["DELETE"])
def api_form_delete(request, form_id):
    try:
        form = Form.objects.get(id=form_id)
        form.delete()
        return JsonResponse({'message': 'Form deleted successfully'})
    except Form.DoesNotExist:
        return JsonResponse({'error': 'Form not found'}, status=404)

# User API Views
@login_required
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def api_users(request):
    users = list(User.objects.values('id', 'username', 'email', 'role'))
    return JsonResponse({'results': users})

@login_required
@user_passes_test(is_admin)
@csrf_exempt
@require_http_methods(["POST"])
def api_users_create(request):
    try:
        data = json.loads(request.body)
        user = User.objects.create_user(
            username=data.get('username'),
            email=data.get('email'),
            password=data.get('password'),
            role=data.get('role', User.ROLE_FACULTY)
        )
        return JsonResponse({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role
        }, status=201)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin)
@csrf_exempt
@require_http_methods(["PUT"])
def api_user_update(request, user_id):
    try:
        data = json.loads(request.body)
        user = User.objects.get(id=user_id)
        user.username = data.get('username', user.username)
        user.email = data.get('email', user.email)
        if 'password' in data and data['password']:
            user.set_password(data['password'])
        user.role = data.get('role', user.role)
        user.save()
        return JsonResponse({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role
        })
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin)
@csrf_exempt
@require_http_methods(["DELETE"])
def api_user_delete(request, user_id):
    try:
        user = User.objects.get(id=user_id)
        # Prevent admin from deleting themselves
        if user == request.user:
            return JsonResponse({'error': 'Cannot delete your own account'}, status=400)
        user.delete()
        return JsonResponse({'message': 'User deleted successfully'})
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)

# CCR Form API Views
@login_required
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def api_ccr_forms(request):
    forms = list(CCRForm.objects.values('id', 'name', 'status', 'created_at'))
    return JsonResponse(forms, safe=False)

@login_required
@user_passes_test(is_admin)
@csrf_exempt
@require_http_methods(["POST"])
def api_ccr_forms_toggle(request):
    try:
        data = json.loads(request.body)
        form_id = data.get('form_id')
        
        ccr_form = CCRForm.objects.get(id=form_id)
        if ccr_form.status == CCRForm.STATUS_ACTIVE:
            ccr_form.status = CCRForm.STATUS_INACTIVE
        else:
            ccr_form.status = CCRForm.STATUS_ACTIVE
        
        ccr_form.save()
        
        return JsonResponse({
            'id': ccr_form.id,
            'name': ccr_form.name,
            'status': ccr_form.status
        })
    except CCRForm.DoesNotExist:
        return JsonResponse({'error': 'CCR Form not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def api_ccr_submissions(request):
    submissions = list(CCRSubmission.objects.select_related('faculty', 'course').values(
        'id', 'faculty__username', 'course__title', 'course__code',
        'course_coordinator', 'submission_date'
    ))
    return JsonResponse(submissions, safe=False)