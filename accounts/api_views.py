from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from .models import Course, Form, User
from django.contrib.auth.decorators import login_required, user_passes_test

def is_admin(user):
    return user.is_authenticated and user.role == User.ROLE_ADMIN

# Course API Views
@login_required
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def api_courses(request):
    courses = list(Course.objects.values('id', 'title', 'code', 'description'))
    return JsonResponse(courses, safe=False)

@login_required
@user_passes_test(is_admin)
@csrf_exempt
@require_http_methods(["POST"])
def api_courses_create(request):
    try:
        data = json.loads(request.body)
        course = Course.objects.create(
            title=data.get('title'),
            code=data.get('code'),
            description=data.get('description', '')
        )
        return JsonResponse({
            'id': course.id,
            'title': course.title,
            'code': course.code,
            'description': course.description
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
        course.save()
        return JsonResponse({
            'id': course.id,
            'title': course.title,
            'code': course.code,
            'description': course.description
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