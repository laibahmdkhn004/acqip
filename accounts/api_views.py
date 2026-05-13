import os
from dotenv import load_dotenv
import litellm
from django.conf import settings
from collections import defaultdict
from datetime import datetime, timedelta, date
import itertools
import re
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import Course, User, Department, DynamicForm, FormQuestion, DynamicFormSubmission, FormAnswer, CourseFaculty, CourseOutline
from django.db.models import Count, Q, F
from datetime import datetime, timedelta

from litellm import completion

        
# Load environment variables
load_dotenv()


def is_admin(user):
    return user.is_authenticated and user.role == User.ROLE_ADMIN

def is_admin_or_crc(user):
    return user.is_authenticated and user.role in [User.ROLE_ADMIN, User.ROLE_CRC_MEMBER]


def course_outline_to_dict(outline):
    """Serialize a CourseOutline for JSON APIs (faculty / CRC)."""
    return {
        'id': outline.id,
        'course': {
            'id': outline.course.id,
            'code': outline.course.code,
            'title': outline.course.title,
        },
        'version': outline.version,
        'title': outline.title,
        'description': outline.description,
        'content': outline.content,
        'status': outline.status,
        'notes': outline.notes,
        'is_current': outline.is_current,
        'faculty_author_id': outline.faculty_id,
        'faculty_author_username': outline.faculty.username,
        'created_at': outline.created_at.isoformat() if outline.created_at else None,
        'submitted_at': outline.submitted_at.isoformat() if outline.submitted_at else None,
        'approved_at': outline.approved_at.isoformat() if outline.approved_at else None,
    }


# Department API Views (list: admin + CRC for course management UI)
@login_required
@user_passes_test(is_admin_or_crc)
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


@login_required
@user_passes_test(is_admin)
@csrf_exempt
@require_http_methods(["GET", "PUT"])
def api_department_detail(request, department_id):
    """Get or update department details"""
    try:
        department = Department.objects.get(id=department_id)
        
        if request.method == 'GET':
            courses = Course.objects.filter(department=department).values(
                'id', 'title', 'code', 'description', 'credits'
            )
            
            courses_list = []
            for course in courses:
                course_data = dict(course)
                course_faculty = CourseFaculty.objects.filter(course_id=course['id']).select_related('faculty')
                faculty_data = []
                for cf in course_faculty:
                    faculty_data.append({
                        'id': cf.faculty.id,
                        'username': cf.faculty.username,
                        'email': cf.faculty.email,
                        'is_coordinator': cf.is_coordinator,
                        'section': cf.section
                    })
                course_data['faculty'] = faculty_data
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
                'total_faculty': CourseFaculty.objects.filter(course__department=department).values('faculty').distinct().count()
            })
        
        elif request.method == 'PUT':
            # Update department
            data = json.loads(request.body)
            
            # Update fields
            if 'name' in data:
                department.name = data['name']
            if 'code' in data:
                department.code = data['code']
            if 'description' in data:
                department.description = data['description']
            
            department.save()
            
            return JsonResponse({
                'id': department.id,
                'name': department.name,
                'code': department.code,
                'description': department.description
            })
            
    except Department.DoesNotExist:
        return JsonResponse({'error': 'Department not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# Course API Views (admin + CRC)
@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_courses(request):
    courses = list(Course.objects.select_related('department').values(
        'id', 'title', 'code', 'description', 'department_id', 'credits', 'department__code'
    ))
    for course in courses:
        course['department_code'] = course.pop('department__code')
        coordinator = CourseFaculty.objects.filter(
            course_id=course['id'], 
            is_coordinator=True
        ).select_related('faculty').first()
        
        if coordinator:
            course['course_coordinator_id'] = coordinator.faculty.id
            course['course_coordinator_name'] = coordinator.faculty.username
            course['coordinator_section'] = coordinator.section
        else:
            course['course_coordinator_id'] = None
            course['course_coordinator_name'] = None
            course['coordinator_section'] = None
    
    return JsonResponse(courses, safe=False)

@csrf_exempt
@login_required
@user_passes_test(is_admin_or_crc)
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
        
        faculty_assignments = data.get('faculty_assignments', [])
        for assignment in faculty_assignments:
            faculty_id = assignment.get('faculty_id')
            is_coordinator = assignment.get('is_coordinator', False)
            section = assignment.get('section', '')
            
            if faculty_id:
                faculty = User.objects.get(id=faculty_id, role=User.ROLE_FACULTY)
                CourseFaculty.objects.create(
                    course=course,
                    faculty=faculty,
                    is_coordinator=is_coordinator,
                    section=section
                )
        
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

@csrf_exempt
@login_required
@user_passes_test(is_admin_or_crc)
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

# Assign/Update Course Faculty
@csrf_exempt
@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["POST"])
def api_assign_course_faculty(request, course_id):
    try:
        data = json.loads(request.body)
        course = Course.objects.get(id=course_id)
        
        # Clear existing assignments
        CourseFaculty.objects.filter(course=course).delete()
        
        # Create new assignments
        faculty_assignments = data.get('faculty_assignments', [])
        
        assignments_created = 0
        for assignment in faculty_assignments:
            faculty_id = assignment.get('faculty_id')
            is_coordinator = assignment.get('is_coordinator', False)
            section = assignment.get('section', '')
            
            if faculty_id:
                try:
                    faculty = User.objects.get(id=faculty_id, role=User.ROLE_FACULTY)
                    CourseFaculty.objects.create(
                        course=course,
                        faculty=faculty,
                        is_coordinator=is_coordinator,
                        section=section
                    )
                    assignments_created += 1
                except User.DoesNotExist:
                    continue
        
        return JsonResponse({
            'message': f'Successfully assigned {assignments_created} faculty to {course.title}',
            'total_assigned': assignments_created,
            'success': True
        })
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found', 'success': False}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e), 'success': False}, status=400)

@csrf_exempt
@login_required
@user_passes_test(is_admin_or_crc)
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
        
        coordinator_info = data.get('coordinator_info', {})
        section_info = data.get('section_info', {})
        
        # Clear existing assignments
        CourseFaculty.objects.filter(faculty=faculty_member).delete()
        
        # Create new assignments
        for course_id in course_ids:
            course = Course.objects.get(id=course_id)
            is_coordinator = coordinator_info.get(str(course_id), False)
            section = section_info.get(str(course_id), '')
            
            CourseFaculty.objects.create(
                course=course,
                faculty=faculty_member,
                is_coordinator=is_coordinator,
                section=section
            )
        
        return JsonResponse({
            'message': f'Successfully assigned {len(course_ids)} courses to {faculty_member.username}'
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
    
    course_assignments = CourseFaculty.objects.filter(faculty=request.user).select_related('course', 'course__department')
    
    courses_data = []
    for assignment in course_assignments:
        courses_data.append({
            'id': assignment.course.id,
            'title': assignment.course.title,
            'code': assignment.course.code,
            'description': assignment.course.description,
            'credits': assignment.course.credits,
            'department_name': assignment.course.department.name if assignment.course.department else '',
            'department_code': assignment.course.department.code if assignment.course.department else '',
            'is_coordinator': assignment.is_coordinator,
            'section': assignment.section
        })
    
    return JsonResponse(courses_data, safe=False)

# Form API Views - Updated for Admin and CRC Member
@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_forms(request):
    forms = list(DynamicForm.objects.values('id', 'name', 'description', 'form_type', 'status'))
    return JsonResponse(forms, safe=False)



# api_views.py - Update api_publish_form
@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["POST"])
def api_publish_form(request, form_id):
    """Publish a form (set status to active) - Allow multiple forms to be active"""
    try:
        form = DynamicForm.objects.get(id=form_id)
        
        # Check if form type is valid (only CCR or CRR)
        if form.form_type not in ['ccr', 'crr']:
            return JsonResponse({'error': 'Cannot publish non-CCR/CRR forms'}, status=400)
        
        # REMOVED: No longer deactivating other forms of the same type
        # Set this form to active
        form.status = 'active'
        form.save()
        
        return JsonResponse({
            'message': f'{form.get_form_type_display()} published successfully',
            'form_id': form.id,
            'form_type': form.form_type,
            'status': form.status
        })
    except DynamicForm.DoesNotExist:
        return JsonResponse({'error': 'Form not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)




@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["POST"])
def api_unpublish_form(request, form_id):
    """Unpublish a form (set status to inactive) - Only for CCR/CRR forms"""
    try:
        form = DynamicForm.objects.get(id=form_id)
        
        # Check if form type is valid (only CCR or CRR)
        if form.form_type not in ['ccr', 'crr']:
            return JsonResponse({'error': 'Cannot unpublish non-CCR/CRR forms'}, status=400)
        
        form.status = 'inactive'
        form.save()
        
        return JsonResponse({
            'message': f'{form.get_form_type_display()} unpublished',
            'form_id': form.id,
            'form_type': form.form_type,
            'status': form.status
        })
    except DynamicForm.DoesNotExist:
        return JsonResponse({'error': 'Form not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["PUT"])
def api_form_update(request, form_id):
    try:
        data = json.loads(request.body)
        form = DynamicForm.objects.get(id=form_id)
        form.name = data.get('name', form.name)
        form.description = data.get('description', form.description)
        form.form_type = data.get('form_type', form.form_type)
        form.status = data.get('status', form.status)
        form.save()
        return JsonResponse({
            'id': form.id,
            'name': form.name,
            'description': form.description,
            'form_type': form.form_type,
            'status': form.status
        })
    except DynamicForm.DoesNotExist:
        return JsonResponse({'error': 'Form not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["DELETE"])
def api_form_delete(request, form_id):
    try:
        form = DynamicForm.objects.get(id=form_id)
        form.delete()
        return JsonResponse({'message': 'Form deleted successfully'})
    except DynamicForm.DoesNotExist:
        return JsonResponse({'error': 'Form not found'}, status=404)

# Dynamic Form API Views
@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_dynamic_forms(request):
    """Get all dynamic forms (ONLY UNIVERSAL CCR/CRR)"""
    forms = list(DynamicForm.objects.filter(
        form_type__in=['ccr', 'crr']  # Only universal forms
    ).values('id', 'name', 'description', 'form_type', 'status', 'created_at'))
    return JsonResponse(forms, safe=False)




@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["POST"])
def api_dynamic_forms_create(request):
    try:
        data = json.loads(request.body)
        form = DynamicForm.objects.create(
            name=data.get('name', 'Dynamic Form'),
            description=data.get('description', ''),
            form_type=data.get('form_type', 'crr'),
            status=data.get('status', DynamicForm.STATUS_INACTIVE)
        )
        return JsonResponse({
            'id': form.id,
            'name': form.name,
            'description': form.description,
            'form_type': form.form_type,
            'status': form.status
        }, status=201)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["PUT"])
def api_dynamic_form_update(request, form_id):
    try:
        data = json.loads(request.body)
        form = DynamicForm.objects.get(id=form_id)
        form.name = data.get('name', form.name)
        form.description = data.get('description', form.description)
        form.form_type = data.get('form_type', form.form_type)
        form.status = data.get('status', form.status)
        form.save()
        return JsonResponse({
            'id': form.id,
            'name': form.name,
            'description': form.description,
            'form_type': form.form_type,
            'status': form.status
        })
    except DynamicForm.DoesNotExist:
        return JsonResponse({'error': 'Dynamic Form not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["DELETE"])
def api_dynamic_form_delete(request, form_id):
    try:
        form = DynamicForm.objects.get(id=form_id)
        form.delete()
        return JsonResponse({'message': 'Dynamic Form deleted successfully'})
    except DynamicForm.DoesNotExist:
        return JsonResponse({'error': 'Dynamic Form not found'}, status=404)

# Form Questions API
@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_form_questions(request, form_id):
    questions = list(FormQuestion.objects.filter(form_id=form_id).values(
        'id', 'question_text', 'question_type', 'order', 'required', 'options', 'config', 'help_text'
    ))
    return JsonResponse(questions, safe=False)

@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["POST"])
def api_form_questions_create(request, form_id):
    try:
        data = json.loads(request.body)
        form = DynamicForm.objects.get(id=form_id)
        
        config = data.get('config')
        if config and isinstance(config, str):
            try:
                config = json.loads(config)
            except:
                config = None
        
        # For CLO percentage questions, ensure proper config
        if data.get('question_type') == 'clo_percentage':
            if not config:
                config = {
                    'clo_fields': ['clo1', 'clo2', 'clo3', 'clo4'],
                    'min_value': 0,
                    'max_value': 100,
                    'step': 0.1,
                    'suffix': '%'
                }
        
        question = FormQuestion.objects.create(
            form=form,
            question_text=data.get('question_text'),
            question_type=data.get('question_type', 'text'),
            order=data.get('order', 0),
            required=data.get('required', True),
            options=data.get('options', ''),
            config=config,
            help_text=data.get('help_text', '')
        )
        return JsonResponse({
            'id': question.id,
            'question_text': question.question_text,
            'question_type': question.question_type,
            'order': question.order,
            'required': question.required,
            'options': question.options,
            'config': question.config,
            'help_text': question.help_text
        }, status=201)
    except Exception as e:
        print(f"Error creating question: {str(e)}")  # Debug logging
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["PUT"])
def api_form_question_update(request, question_id):
    try:
        data = json.loads(request.body)
        question = FormQuestion.objects.get(id=question_id)
        question.question_text = data.get('question_text', question.question_text)
        question.question_type = data.get('question_type', question.question_type)
        question.order = data.get('order', question.order)
        question.required = data.get('required', question.required)
        question.options = data.get('options', question.options)
        question.help_text = data.get('help_text', question.help_text)
        
        config = data.get('config')
        if config is not None:
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except:
                    config = None
            question.config = config
        
        question.save()
        return JsonResponse({
            'id': question.id,
            'question_text': question.question_text,
            'question_type': question.question_type,
            'order': question.order,
            'required': question.required,
            'options': question.options,
            'config': question.config,
            'help_text': question.help_text
        })
    except FormQuestion.DoesNotExist:
        return JsonResponse({'error': 'Question not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["DELETE"])
def api_form_question_delete(request, question_id):
    try:
        question = FormQuestion.objects.get(id=question_id)
        question.delete()
        return JsonResponse({'message': 'Question deleted successfully'})
    except FormQuestion.DoesNotExist:
        return JsonResponse({'error': 'Question not found'}, status=404)

# Dynamic Form Submissions API
@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_dynamic_submissions(request):
    form_type = request.GET.get('form_type')
    faculty_id = request.GET.get('faculty_id')
    course_id = request.GET.get('course_id')
    
    submissions = DynamicFormSubmission.objects.all().select_related(
        'faculty', 'course', 'dynamic_form'
    )
    
    # Apply filters
    if form_type:
        submissions = submissions.filter(dynamic_form__form_type=form_type)
    if faculty_id:
        submissions = submissions.filter(faculty_id=faculty_id)
    if course_id:
        submissions = submissions.filter(course_id=course_id)
    
    submissions_list = list(submissions.order_by('-submission_date').values(
        'id', 'faculty__username', 'faculty__email', 'course__title', 'course__code',
        'course_coordinator', 'is_coordinator', 'status', 'submission_date', 
        'dynamic_form__name', 'dynamic_form__form_type', 'section'
    ))
    
    return JsonResponse(submissions_list, safe=False)

# Get active form and questions for faculty
@login_required
@require_http_methods(["GET"])
def api_faculty_dynamic_forms(request):
    """Get active forms for faculty - UNIVERSAL FORMS"""
    if request.user.role != User.ROLE_FACULTY:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        form_type = request.GET.get('form_type')  # 'ccr' or 'crr'
        course_id = request.GET.get('course_id')
        
        # If course_id is provided but form_type is not, try to determine form_type
        if course_id and not form_type:
            try:
                course_assignment = CourseFaculty.objects.get(
                    faculty=request.user,
                    course_id=course_id
                )
                # If user is coordinator, default to CCR, otherwise CRR
                form_type = 'ccr' if course_assignment.is_coordinator else 'crr'
            except CourseFaculty.DoesNotExist:
                return JsonResponse({'error': 'Course not assigned to you'}, status=400)
        
        if not form_type:
            return JsonResponse({'error': 'form_type is required'}, status=400)
        
        # Validate form type
        if form_type not in ['ccr', 'crr']:
            return JsonResponse({'error': 'Invalid form type. Must be "ccr" or "crr"'}, status=400)
        
        # Check if user can access this form type
        if form_type == 'ccr':
            is_coordinator_for_any = CourseFaculty.objects.filter(
                faculty=request.user,
                is_coordinator=True
            ).exists()
            if not is_coordinator_for_any:
                return JsonResponse({'error': 'Only course coordinators can access CCR forms'}, status=403)
        
        # Get ALL active forms of the appropriate type
        active_forms = DynamicForm.objects.filter(
            status=DynamicForm.STATUS_ACTIVE,
            form_type=form_type
        )
        
        if not active_forms.exists():
            return JsonResponse({
                'active': False, 
                'message': f'No active {form_type.upper()} form available'
            })
        
        # Get all courses assigned to this faculty
        course_assignments = CourseFaculty.objects.filter(
            faculty=request.user
        ).select_related('course').order_by('course__code')
        
        assigned_courses = []
        for assignment in course_assignments:
            # For CCR form, only show courses where user is coordinator
            if form_type == 'ccr' and not assignment.is_coordinator:
                continue
                
            assigned_courses.append({
                'id': assignment.course.id,
                'code': assignment.course.code,
                'title': assignment.course.title,
                'is_coordinator': assignment.is_coordinator,
                'section': assignment.section,
            })
        
        # Get questions for ALL active forms
        forms_with_questions = []
        for form in active_forms:
            questions = list(FormQuestion.objects.filter(form=form).order_by('order').values(
                'id', 'question_text', 'question_type', 'required', 'options', 'config', 'help_text'
            ))
            
            forms_with_questions.append({
                'id': form.id,
                'name': form.name,
                'description': form.description,
                'form_type': form.form_type,
                'questions': questions
            })
        
        return JsonResponse({
            'active': True,
            'forms': forms_with_questions,  # Now returns array of forms
            'assigned_courses': assigned_courses
        })
        
    except Exception as e:
        print(f"Error in api_faculty_dynamic_forms: {str(e)}")  # For debugging
        return JsonResponse({'error': str(e)}, status=400)

# Check form availability for faculty

@login_required
@require_http_methods(["GET"])
def api_form_availability(request):
    """Check which universal forms (CCR/CRR) are available for faculty"""
    if request.user.role != User.ROLE_FACULTY:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        # Get ALL active forms for CCR and CRR
        ccr_forms = list(DynamicForm.objects.filter(
            status=DynamicForm.STATUS_ACTIVE,
            form_type='ccr'
        ).values('id', 'name', 'description', 'created_at').order_by('-created_at'))
        
        crr_forms = list(DynamicForm.objects.filter(
            status=DynamicForm.STATUS_ACTIVE,
            form_type='crr'
        ).values('id', 'name', 'description', 'created_at').order_by('-created_at'))
        
        # Check if user is coordinator for ANY course
        is_coordinator_for_any = CourseFaculty.objects.filter(
            faculty=request.user,
            is_coordinator=True
        ).exists()
        
        # Get assigned courses
        course_assignments = CourseFaculty.objects.filter(
            faculty=request.user
        ).select_related('course')
        
        courses_data = []
        for assignment in course_assignments:
            courses_data.append({
                'course_id': assignment.course.id,
                'course_code': assignment.course.code,
                'course_title': assignment.course.title,
                'is_coordinator': assignment.is_coordinator,
                'section': assignment.section,
                'forms_available': {
                    'ccr': ccr_forms if assignment.is_coordinator else [],
                    'crr': crr_forms
                }
            })
        
        return JsonResponse({
            'active_forms': {
                'ccr': ccr_forms,
                'crr': crr_forms
            },
            'user_can_submit_ccr': len(ccr_forms) > 0 and is_coordinator_for_any,
            'user_can_submit_crr': len(crr_forms) > 0,
            'courses': courses_data,
            'status': 'success'
        })
    except Exception as e:
        print(f"Error in api_form_availability: {str(e)}")
        return JsonResponse({
            'error': str(e),
            'status': 'error',
            'active_forms': {'ccr': [], 'crr': []},
            'user_can_submit_ccr': False,
            'user_can_submit_crr': False,
            'courses': []
        }, status=400)

# Submit universal form
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_submit_dynamic_form(request):
    """Submit UNIVERSAL form (CCR/CRR) for a specific course"""
    if request.user.role != User.ROLE_FACULTY:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        data = json.loads(request.body)
        course_id = data.get('course_id')
        form_id = data.get('form_id')  # Now form_id is required since multiple forms
        answers = data.get('answers', {})
        status = data.get('status', 'draft')  # 'draft' or 'submitted'
        
        print(f"Form submission attempt: user={request.user.username}, course_id={course_id}, form_id={form_id}, status={status}")
        
        if not form_id:
            return JsonResponse({'error': 'form_id is required. Multiple forms may be active.'}, status=400)
        
        # Validate course assignment
        try:
            course_assignment = CourseFaculty.objects.get(
                faculty=request.user,
                course_id=course_id
            )
        except CourseFaculty.DoesNotExist:
            return JsonResponse({'error': 'Course not assigned to you'}, status=400)
        
        # Get the SPECIFIC UNIVERSAL form
        try:
            form = DynamicForm.objects.get(id=form_id, form_type__in=['ccr', 'crr'])
        except DynamicForm.DoesNotExist:
            return JsonResponse({'error': 'Form not found or not a universal form'}, status=404)
        
        # Check if form is active
        if form.status != 'active':
            return JsonResponse({'error': 'Form is not active'}, status=400)
        
        # Check if form type matches coordinator status
        if form.form_type == 'ccr' and not course_assignment.is_coordinator:
            return JsonResponse({'error': 'Only course coordinators can submit CCR forms'}, status=403)
        
        # Get course
        course = Course.objects.get(id=course_id)
        
        # Check if already submitted (if this is a submission, not draft)
        existing_submission = DynamicFormSubmission.objects.filter(
            faculty=request.user,
            course_id=course_id,
            dynamic_form=form
        ).first()
        
        # Allow resubmission if in draft or revision requested status
        # Only block if trying to submit when already submitted
        if existing_submission and existing_submission.status == 'submitted' and status == 'submitted':
            return JsonResponse({
                'error': 'You have already submitted this form for the selected course.',
                'submission_id': existing_submission.id,
                'status': existing_submission.status
            }, status=400)
        
        # Create or update submission
        if existing_submission:
            submission = existing_submission
            submission.status = status
            
            # Update submission date if submitting (not draft)
            if status == 'submitted':
                submission.submission_date = datetime.now()
            
            submission.save()
            
            # Delete existing answers
            FormAnswer.objects.filter(submission=submission).delete()
        else:
            submission = DynamicFormSubmission.objects.create(
                dynamic_form=form,
                faculty=request.user,
                course=course,
                course_code_title=f"{course.code} - {course.title}",
                course_coordinator=request.user.username if course_assignment.is_coordinator else "",
                is_coordinator=course_assignment.is_coordinator,
                section=course_assignment.section,
                status=status,
                submission_date=datetime.now() if status == 'submitted' else None
            )
        
        # Create answers
        for question_id, answer_value in answers.items():
            try:
                question = FormQuestion.objects.get(id=question_id, form=form)
                
                # Handle different answer types
                if isinstance(answer_value, (list, dict)):
                    FormAnswer.objects.create(
                        submission=submission,
                        question=question,
                        answer_text="",
                        answer_data=answer_value
                    )
                else:
                    FormAnswer.objects.create(
                        submission=submission,
                        question=question,
                        answer_text=str(answer_value) if answer_value is not None else "",
                        answer_data=None
                    )
            except FormQuestion.DoesNotExist:
                print(f"Warning: Question {question_id} not found in form {form_id}")
                continue
        
        return JsonResponse({
            'message': f'Form {"submitted" if status == "submitted" else "saved as draft"} successfully!',
            'submission_id': submission.id,
            'status': submission.status,
            'success': True
        })
        
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    except Exception as e:
        print(f"Error in form submission: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': f'Submission failed: {str(e)}'}, status=400)

# Faculty Users API
@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_faculty_users(request):
    try:
        faculty_users = list(User.objects.filter(role=User.ROLE_FACULTY).values(
            'id', 'username', 'email', 'department', 'designation'
        ))
        return JsonResponse({'results': faculty_users})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

# Course Faculty Assignments API
@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_course_faculty_assignments(request, course_id):
    try:
        assignments = CourseFaculty.objects.filter(course_id=course_id).values(
            'faculty_id', 'is_coordinator', 'section'
        )
        return JsonResponse(list(assignments), safe=False)
    except Exception as e:
        return JsonResponse([], safe=False)

# User API Views
@login_required
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def api_users(request):
    users = list(User.objects.values('id', 'username', 'email', 'role', 'department', 'designation'))
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
            role=data.get('role', User.ROLE_FACULTY),
            department=data.get('department', ''),
            designation=data.get('designation', '')
        )
        return JsonResponse({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'department': user.department,
            'designation': user.designation
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
        user.department = data.get('department', user.department)
        user.designation = data.get('designation', user.designation)
        user.save()
        return JsonResponse({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'department': user.department,
            'designation': user.designation
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
        if user == request.user:
            return JsonResponse({'error': 'Cannot delete your own account'}, status=400)
        user.delete()
        return JsonResponse({'message': 'User deleted successfully'})
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)

# CRC Specific APIs
@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_crc_faculty_list(request):
    """Get all faculty with their assigned courses and coordinator status"""
    try:
        faculty_list = []
        
        # Get all faculty users
        faculty_users = User.objects.filter(role=User.ROLE_FACULTY).prefetch_related('coursefaculty_set__course')
        
        for faculty in faculty_users:
            # Get course assignments
            assignments = CourseFaculty.objects.filter(faculty=faculty).select_related('course')
            
            assigned_courses = []
            coordinator_courses = []
            
            for assignment in assignments:
                course_data = {
                    'id': assignment.course.id,
                    'code': assignment.course.code,
                    'title': assignment.course.title,
                    'section': assignment.section,
                    'is_coordinator': assignment.is_coordinator
                }
                
                assigned_courses.append(course_data)
                if assignment.is_coordinator:
                    coordinator_courses.append(course_data)
            
            faculty_list.append({
                'id': faculty.id,
                'username': faculty.username,
                'email': faculty.email,
                'department': faculty.department,
                'designation': faculty.designation,
                'total_courses': len(assigned_courses),
                'coordinator_courses_count': len(coordinator_courses),
                'assigned_courses': assigned_courses,
                'coordinator_courses': coordinator_courses
            })
        
        return JsonResponse({
            'total_faculty': len(faculty_list),
            'faculty': faculty_list
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_crc_course_catalogue(request):
    """Get all course outlines (both old and new)"""
    try:
        # Get all courses with their outlines
        courses = Course.objects.prefetch_related('outlines').all()
        
        catalogue = []
        for course in courses:
            # Get current official outline
            current_outline = course.outlines.filter(is_current=True, status='approved').first()
            
            # Get all outlines for this course
            all_outlines = list(course.outlines.order_by('-version').values(
                'id', 'version', 'title', 'status', 'is_current', 
                'faculty__username', 'created_at', 'submitted_at', 'approved_at'
            ))
            
            catalogue.append({
                'course_id': course.id,
                'course_code': course.code,
                'course_title': course.title,
                'department': course.department.name if course.department else '',
                'current_outline': {
                    'id': current_outline.id if current_outline else None,
                    'version': current_outline.version if current_outline else None,
                    'title': current_outline.title if current_outline else '',
                    'faculty': current_outline.faculty.username if current_outline else ''
                } if current_outline else None,
                'total_outlines': len(all_outlines),
                'outlines': all_outlines
            })
        
        return JsonResponse(catalogue, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["POST"])
def api_crc_update_course_outline(request):
    """Update course outline (edit/upload new version)"""
    try:
        data = json.loads(request.body)
        outline_id = data.get('outline_id')
        action = data.get('action')  # 'approve', 'request_revision', 'update'
        notes = data.get('notes', '')
        
        if action == 'approve':
            outline = CourseOutline.objects.get(id=outline_id)
            
            # Set this outline as approved and current
            outline.status = 'approved'
            outline.approved_at = datetime.now()
            outline.is_current = True
            outline.notes = notes
            
            # Mark other outlines as not current
            CourseOutline.objects.filter(course=outline.course).exclude(id=outline_id).update(is_current=False)
            
            outline.save()
            
            return JsonResponse({
                'message': 'Course outline approved and set as current',
                'outline_id': outline.id,
                'status': outline.status,
                'approved_at': outline.approved_at.isoformat()
            })
            
        elif action == 'request_revision':
            outline = CourseOutline.objects.get(id=outline_id)
            
            # Only request revision on submitted outlines
            if outline.status != 'submitted':
                return JsonResponse({
                    'error': f'Cannot request revision on outline with status: {outline.status}'
                }, status=400)
            
            outline.status = 'revision_requested'
            outline.notes = notes
            outline.save()
            
            return JsonResponse({
                'message': 'Revision requested for course outline',
                'outline_id': outline.id,
                'status': outline.status,
                'notes': outline.notes
            })
            
        elif action == 'update':
            outline = CourseOutline.objects.get(id=outline_id)
            outline.title = data.get('title', outline.title)
            outline.description = data.get('description', outline.description)
            outline.content = data.get('content', outline.content)
            outline.notes = data.get('notes', outline.notes)
            outline.save()
            
            return JsonResponse({
                'message': 'Course outline updated',
                'outline_id': outline.id
            })
            
        else:
            return JsonResponse({'error': 'Invalid action'}, status=400)
            
    except CourseOutline.DoesNotExist:
        return JsonResponse({'error': 'Course outline not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_http_methods(["GET"])
def api_check_outline_permissions(request, outline_id):
    """Check if faculty can edit a course outline"""
    if request.user.role != User.ROLE_FACULTY:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        outline = CourseOutline.objects.get(id=outline_id, faculty=request.user)
        
        can_edit = outline.status in ['draft', 'revision_requested']
        
        return JsonResponse({
            'can_edit': can_edit,
            'status': outline.status,
            'notes': outline.notes if not can_edit else '',
            'message': 'Can edit' if can_edit else f'Cannot edit: Outline is {outline.status}'
        })
    except CourseOutline.DoesNotExist:
        return JsonResponse({'error': 'Outline not found or access denied'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_crc_course_outline_submissions(request):
    """Get all course outline submissions (new outlines waiting for approval)"""
    try:
        submissions = CourseOutline.objects.filter(
            status__in=['submitted', 'revision_requested']
        ).select_related('course', 'faculty').order_by('-submitted_at')
        
        submissions_list = list(submissions.values(
            'id', 'course__code', 'course__title', 'faculty__username',
            'version', 'title', 'status', 'submitted_at', 'notes'
        ))
        
        return JsonResponse(submissions_list, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_crc_form_submissions(request):
    """Get all form submissions with filtering options (UNIVERSAL FORMS ONLY)"""
    try:
        faculty_id = request.GET.get('faculty_id')
        course_id = request.GET.get('course_id')
        department_id = request.GET.get('department_id')
        form_type = request.GET.get('form_type')
        
        submissions = DynamicFormSubmission.objects.filter(
            dynamic_form__form_type__in=['ccr', 'crr']  # Only universal forms
        ).select_related(
            'faculty', 'course', 'dynamic_form', 'course__department'
        )
        
        # Apply filters
        if faculty_id:
            submissions = submissions.filter(faculty_id=faculty_id)
        if course_id:
            submissions = submissions.filter(course_id=course_id)
        if department_id:
            submissions = submissions.filter(course__department_id=department_id)
        if form_type:
            submissions = submissions.filter(dynamic_form__form_type=form_type)
        
        submissions_list = list(submissions.order_by('-submission_date').values(
            'id', 'faculty__username', 'faculty__email', 'faculty__department',
            'course__code', 'course__title', 'course__department__name',
            'dynamic_form__name', 'dynamic_form__form_type',
            'status', 'is_coordinator', 'submission_date', 'section'
        ))
        
        return JsonResponse(submissions_list, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_save_course_outline(request):
    """Save or update course outline (faculty coordinators or CRC members)."""
    if request.user.role not in (User.ROLE_FACULTY, User.ROLE_CRC_MEMBER):
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        data = json.loads(request.body)
        course_id = data.get('course_id')
        outline_id = data.get('outline_id')
        content = data.get('content')
        title = data.get('title', 'Course Outline')
        description = data.get('description', '')
        status = data.get('status', 'draft')  # 'draft' or 'submitted'
        
        if not course_id:
            return JsonResponse({'error': 'course_id is required'}, status=400)
        
        if not content:
            return JsonResponse({'error': 'content is required'}, status=400)
        
        if request.user.role == User.ROLE_FACULTY:
            try:
                CourseFaculty.objects.get(
                    faculty=request.user,
                    course_id=course_id,
                    is_coordinator=True
                )
            except CourseFaculty.DoesNotExist:
                return JsonResponse({'error': 'Only course coordinators can save course outlines'}, status=403)
        
        course = Course.objects.get(id=course_id)
        
        if outline_id:
            # Update existing outline
            outline = CourseOutline.objects.get(id=outline_id, faculty=request.user)
            
            # WORKFLOW RESTRICTIONS
            if outline.status == 'approved':
                return JsonResponse({
                    'error': 'Cannot edit an approved outline. Create a new version instead.',
                    'approved': True
                }, status=400)
            
            if outline.status == 'submitted' and status == 'draft':
                return JsonResponse({
                    'error': 'Cannot change submitted outline back to draft. Wait for CRC review.',
                    'submitted': True
                }, status=400)
            
            # Allow editing only in draft or revision_requested status
            if outline.status not in ['draft', 'revision_requested'] and status == 'draft':
                return JsonResponse({
                    'error': f'Cannot edit outline in {outline.status} status',
                    'current_status': outline.status
                }, status=400)
            
            # If CRC requested revision, allow saving as draft or submitted
            if outline.status == 'revision_requested':
                # Clear notes when faculty starts editing (only if saving as draft)
                if status == 'draft':
                    outline.notes = ''
            
            outline.title = title
            outline.description = description
            outline.content = content
            outline.status = status
            
            if status == 'submitted' and outline.status != 'submitted':
                outline.submitted_at = datetime.now()
            
            outline.save()
        else:
            # Create new outline
            # Get latest version
            latest_version = CourseOutline.objects.filter(
                course=course, faculty=request.user
            ).order_by('-version').first()
            
            new_version = (latest_version.version + 1) if latest_version else 1
            
            outline = CourseOutline.objects.create(
                course=course,
                faculty=request.user,
                version=new_version,
                title=title,
                description=description,
                content=content,
                status=status
            )
            
            if status == 'submitted':
                outline.submitted_at = datetime.now()
                outline.save()
        
        return JsonResponse({
            'message': 'Course outline saved successfully',
            'outline_id': outline.id,
            'version': outline.version,
            'status': outline.status,
            'submitted_at': outline.submitted_at.isoformat() if outline.submitted_at else None,
            'notes': outline.notes,
            'can_edit': outline.status in ['draft', 'revision_requested']
        })
        
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    except CourseOutline.DoesNotExist:
        return JsonResponse({'error': 'Course outline not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_crc_view_outline_content(request, outline_id):
    """CRC member can view the actual content of a course outline"""
    try:
        outline = CourseOutline.objects.get(id=outline_id)
        
        # Parse content if it's JSON, otherwise return as-is
        content = outline.content
        try:
            if content and isinstance(content, str):
                content = json.loads(content)
        except:
            pass  # Keep as string if not JSON
        
        return JsonResponse({
            'id': outline.id,
            'course': {
                'id': outline.course.id,
                'code': outline.course.code,
                'title': outline.course.title,
                'credits': outline.course.credits,
                'department': outline.course.department.name if outline.course.department else ''
            },
            'faculty': {
                'id': outline.faculty.id,
                'username': outline.faculty.username,
                'email': outline.faculty.email,
                'department': outline.faculty.department,
                'designation': outline.faculty.designation
            },
            'version': outline.version,
            'title': outline.title,
            'description': outline.description,
            'content': content,
            'status': outline.status,
            'is_current': outline.is_current,
            'notes': outline.notes,
            'created_at': outline.created_at.isoformat() if outline.created_at else None,
            'submitted_at': outline.submitted_at.isoformat() if outline.submitted_at else None,
            'approved_at': outline.approved_at.isoformat() if outline.approved_at else None,
            'can_edit': outline.status in ['draft', 'revision_requested']  # For faculty reference
        })
    except CourseOutline.DoesNotExist:
        return JsonResponse({'error': 'Course outline not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@require_http_methods(["GET"])
def api_get_course_outline(request):
    """Get course outline: faculty (assigned/coordinator rules); CRC (any outline by id, own drafts by course)."""
    if request.user.role not in (User.ROLE_FACULTY, User.ROLE_CRC_MEMBER):
        return JsonResponse({'error': 'Access denied'}, status=403)

    outline_id = request.GET.get('outline_id')
    course_id = request.GET.get('course_id')

    try:
        if request.user.role == User.ROLE_CRC_MEMBER:
            if outline_id:
                outline = CourseOutline.objects.select_related('course', 'faculty').get(
                    id=outline_id
                )
                return JsonResponse(course_outline_to_dict(outline))
            if not course_id:
                return JsonResponse(
                    {'error': 'course_id or outline_id is required'},
                    status=400,
                )
            Course.objects.get(id=course_id)
            outline = CourseOutline.objects.filter(
                course_id=course_id,
                faculty=request.user,
            ).select_related('course', 'faculty').order_by('-version').first()
            if outline:
                return JsonResponse(course_outline_to_dict(outline))
            return JsonResponse({'exists': False})

        def faculty_assigned_to_course(course_pk):
            return CourseFaculty.objects.filter(
                faculty=request.user,
                course_id=course_pk,
            ).exists()

        def faculty_is_coordinator_for_course(course_pk):
            return CourseFaculty.objects.filter(
                faculty=request.user,
                course_id=course_pk,
                is_coordinator=True,
            ).exists()

        if outline_id:
            outline = CourseOutline.objects.select_related('course', 'faculty').get(
                id=outline_id
            )
            if not faculty_assigned_to_course(outline.course_id):
                return JsonResponse({'error': 'Access denied'}, status=403)
            return JsonResponse(course_outline_to_dict(outline))

        if not course_id:
            return JsonResponse(
                {'error': 'course_id or outline_id is required'},
                status=400,
            )

        if not faculty_assigned_to_course(course_id):
            return JsonResponse({'error': 'Access denied'}, status=403)

        if faculty_is_coordinator_for_course(course_id):
            outline = CourseOutline.objects.filter(
                course_id=course_id,
                faculty=request.user,
            ).select_related('course', 'faculty').order_by('-version').first()
        else:
            outline = (
                CourseOutline.objects.filter(
                    course_id=course_id,
                    is_current=True,
                )
                .select_related('course', 'faculty')
                .order_by('-version')
                .first()
            )
            if not outline:
                outline = (
                    CourseOutline.objects.filter(
                        course_id=course_id,
                        status=CourseOutline.STATUS_APPROVED,
                    )
                    .select_related('course', 'faculty')
                    .order_by('-version')
                    .first()
                )
            if not outline:
                outline = (
                    CourseOutline.objects.filter(course_id=course_id)
                    .select_related('course', 'faculty')
                    .order_by('-version')
                    .first()
                )

        if outline:
            return JsonResponse(course_outline_to_dict(outline))
        return JsonResponse({'exists': False})

    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    except CourseOutline.DoesNotExist:
        return JsonResponse({'error': 'Course outline not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)



# Submission Details API
@login_required
@require_http_methods(["GET"])
def api_submission_details(request, submission_id):
    """Get detailed information about a specific submission"""
    try:
        submission = DynamicFormSubmission.objects.get(id=submission_id)
        
        # Check permissions
        if request.user.role == User.ROLE_FACULTY and submission.faculty != request.user:
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        # Get all answers for this submission
        answers = FormAnswer.objects.filter(submission=submission).select_related('question')
        
        answers_data = []
        for answer in answers:
            answers_data.append({
                'question_id': answer.question.id,
                'question_text': answer.question.question_text,
                'question_type': answer.question.question_type,
                'answer_text': answer.answer_text,
                'answer_data': answer.answer_data
            })
        
        return JsonResponse({
            'id': submission.id,
            'course_code': submission.course.code,
            'course_title': submission.course.title,
            'form_name': submission.dynamic_form.name,
            'form_type': submission.dynamic_form.form_type,
            'faculty_name': submission.faculty.username,
            'faculty_email': submission.faculty.email,
            'faculty_department': submission.faculty.department,
            'is_coordinator': submission.is_coordinator,
            'status': submission.status,
            'section': submission.section,
            'submission_date': submission.submission_date.strftime('%B %d, %Y at %I:%M %p'),
            'answers': answers_data
        })
        
    except DynamicFormSubmission.DoesNotExist:
        return JsonResponse({'error': 'Submission not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

# CRC Dashboard Statistics API
@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_crc_dashboard_stats(request):
    """Get comprehensive statistics for CRC dashboard (UNIVERSAL FORMS ONLY)"""
    try:
        # Total faculty count
        total_faculty = User.objects.filter(role=User.ROLE_FACULTY).count()
        
        # Total courses count
        total_courses = Course.objects.count()
        
        # Pending course outlines (submitted but not approved)
        pending_outlines = CourseOutline.objects.filter(status='submitted').count()
        
        # Total form submissions (UNIVERSAL FORMS ONLY)
        total_submissions = DynamicFormSubmission.objects.filter(
            status='submitted',
            dynamic_form__form_type__in=['ccr', 'crr']
        ).count()
        
        # Recent submissions (last 7 days) - UNIVERSAL FORMS ONLY
        week_ago = datetime.now() - timedelta(days=7)
        recent_submissions = DynamicFormSubmission.objects.filter(
            status='submitted',
            submission_date__gte=week_ago,
            dynamic_form__form_type__in=['ccr', 'crr']  # Only universal forms
        ).count()
        
        # Faculty with most submissions (UNIVERSAL FORMS ONLY)
        faculty_submission_counts = DynamicFormSubmission.objects.filter(
            status='submitted',
            dynamic_form__form_type__in=['ccr', 'crr']  # Only universal forms
        ).values('faculty__username').annotate(
            count=Count('id')
        ).order_by('-count')[:5]
        
        # Forms status (active/inactive) - ONLY CCR and CRR
        form_status = {
            'ccr_active': DynamicForm.objects.filter(form_type='ccr', status='active').exists(),
            'crr_active': DynamicForm.objects.filter(form_type='crr', status='active').exists(),
        }
        
        # Departments with most courses
        department_stats = Department.objects.annotate(
            course_count=Count('courses')
        ).order_by('-course_count').values('name', 'code', 'course_count')[:5]
        
        return JsonResponse({
            'total_faculty': total_faculty,
            'total_courses': total_courses,
            'pending_outlines': pending_outlines,
            'total_submissions': total_submissions,
            'recent_submissions': recent_submissions,
            'top_faculty_submissions': list(faculty_submission_counts),
            'form_status': form_status,
            'department_stats': list(department_stats),
            'generated_at': datetime.now().isoformat()
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# Submission Approval APIs
@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["POST"])
def api_approve_submission(request, submission_id):
    """Approve a form submission"""
    try:
        submission = DynamicFormSubmission.objects.get(id=submission_id)
        submission.status = 'approved'
        submission.save()
        
        return JsonResponse({
            'message': 'Submission approved successfully',
            'submission_id': submission.id,
            'status': submission.status
        })
    except DynamicFormSubmission.DoesNotExist:
        return JsonResponse({'error': 'Submission not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["POST"])
def api_reject_submission(request, submission_id):
    """Reject a form submission"""
    try:
        submission = DynamicFormSubmission.objects.get(id=submission_id)
        submission.status = 'revision_requested'
        submission.save()
        
        return JsonResponse({
            'message': 'Submission rejected and revision requested',
            'submission_id': submission.id,
            'status': submission.status
        })
    except DynamicFormSubmission.DoesNotExist:
        return JsonResponse({'error': 'Submission not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["POST"])
def api_request_revision_submission(request, submission_id):
    """Request revision for a submission"""
    try:
        data = json.loads(request.body)
        notes = data.get('notes', '')
        
        submission = DynamicFormSubmission.objects.get(id=submission_id)
        submission.status = 'revision_requested'
        
        submission.save()
        
        return JsonResponse({
            'message': 'Revision requested for submission',
            'submission_id': submission.id,
            'status': submission.status,
            'notes': notes
        })
    except DynamicFormSubmission.DoesNotExist:
        return JsonResponse({'error': 'Submission not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

# Admin Faculty Management - Password Reset
@login_required
@user_passes_test(is_admin)
@csrf_exempt
@require_http_methods(["POST"])
def api_admin_reset_faculty_password(request, user_id):
    """Reset faculty password (admin only)"""
    try:
        data = json.loads(request.body)
        new_password = data.get('new_password')
        
        if not new_password:
            return JsonResponse({'error': 'New password is required'}, status=400)
        
        user = User.objects.get(id=user_id, role=User.ROLE_FACULTY)
        user.set_password(new_password)
        user.save()
        
        return JsonResponse({
            'message': f'Password reset successfully for {user.username}',
            'user_id': user.id,
            'username': user.username
        })
    except User.DoesNotExist:
        return JsonResponse({'error': 'Faculty user not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

# Faculty Submissions API
@login_required
@require_http_methods(["GET"])
def api_faculty_submissions(request):
    """Get all submissions for the current faculty member (UNIVERSAL FORMS ONLY)"""
    if request.user.role != User.ROLE_FACULTY:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        submissions = DynamicFormSubmission.objects.filter(
            faculty=request.user,
            dynamic_form__form_type__in=['ccr', 'crr']  # Only universal forms
        ).select_related('course', 'dynamic_form').order_by('-submission_date')
        
        submissions_list = []
        for submission in submissions:
            # Get answer count for this submission
            answer_count = FormAnswer.objects.filter(submission=submission).count()
            
            submissions_list.append({
                'id': submission.id,
                'course': {
                    'id': submission.course.id,
                    'code': submission.course.code,
                    'title': submission.course.title
                },
                'dynamic_form': {
                    'id': submission.dynamic_form.id,
                    'name': submission.dynamic_form.name,
                    'form_type': submission.dynamic_form.form_type
                },
                'status': submission.status,
                'is_coordinator': submission.is_coordinator,
                'submission_date': submission.submission_date.isoformat() if submission.submission_date else None,
                'answer_count': answer_count,
                'section': submission.section
            })
        
        return JsonResponse(submissions_list, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

# Faculty Course Outlines API
@login_required
@require_http_methods(["GET"])
def api_faculty_course_outlines(request):
    """Faculty: outlines for assigned courses. CRC: all outlines that have entered review (not drafts)."""
    if request.user.role not in (User.ROLE_FACULTY, User.ROLE_CRC_MEMBER):
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        if request.user.role == User.ROLE_CRC_MEMBER:
            outlines = CourseOutline.objects.filter(
                status__in=[
                    CourseOutline.STATUS_SUBMITTED,
                    CourseOutline.STATUS_REVISION,
                    CourseOutline.STATUS_APPROVED,
                ]
            ).select_related('course', 'faculty').order_by('-submitted_at', '-approved_at', '-updated_at', '-id')
        else:
            assigned_course_ids = CourseFaculty.objects.filter(
                faculty=request.user
            ).values_list('course_id', flat=True)

            outlines = CourseOutline.objects.filter(
                course_id__in=assigned_course_ids
            ).select_related('course', 'faculty').order_by('course_id', '-version', '-created_at')
        
        outlines_list = []
        for outline in outlines:
            is_author = outline.faculty_id == request.user.id
            can_edit = is_author and outline.status in [
                CourseOutline.STATUS_DRAFT,
                CourseOutline.STATUS_REVISION,
            ]
            can_submit = can_edit
            outlines_list.append({
                'id': outline.id,
                'course': {
                    'id': outline.course.id,
                    'code': outline.course.code,
                    'title': outline.course.title
                },
                'version': outline.version,
                'title': outline.title,
                'description': outline.description,
                'status': outline.status,
                'is_current': outline.is_current,
                'notes': outline.notes,
                'faculty_author_id': outline.faculty_id,
                'faculty_author_username': outline.faculty.username,
                'can_edit': can_edit,
                'can_submit': can_submit,
                'created_at': outline.created_at.isoformat() if outline.created_at else None,
                'submitted_at': outline.submitted_at.isoformat() if outline.submitted_at else None,
                'approved_at': outline.approved_at.isoformat() if outline.approved_at else None
            })
        
        return JsonResponse(outlines_list, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

# Faculty Profile Update API
@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_faculty_profile_update(request):
    """Update faculty profile information"""
    if request.user.role != User.ROLE_FACULTY:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        data = json.loads(request.body)
        user = request.user
        
        if 'email' in data:
            user.email = data['email']
        
        if 'department' in data:
            user.department = data['department']
        
        if 'designation' in data:
            user.designation = data['designation']
        
        user.save()
        
        return JsonResponse({
            'message': 'Profile updated successfully',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'department': user.department,
                'designation': user.designation
            }
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

# Faculty Submissions API (simple version)
@login_required
@require_http_methods(["GET"])
def api_faculty_submissions_list(request):
    """Get all form submissions for the faculty member"""
    if request.user.role != User.ROLE_FACULTY:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        submissions = DynamicFormSubmission.objects.filter(
            faculty=request.user
        ).select_related('course', 'dynamic_form').order_by('-submission_date')
        
        submissions_list = []
        for submission in submissions:
            answer_count = FormAnswer.objects.filter(submission=submission).count()
            submissions_list.append({
                'id': submission.id,
                'course': {
                    'id': submission.course.id,
                    'title': submission.course.title,
                    'code': submission.course.code
                },
                'dynamic_form': {
                    'id': submission.dynamic_form.id,
                    'name': submission.dynamic_form.name,
                    'form_type': submission.dynamic_form.form_type
                },
                'status': submission.status,
                'is_coordinator': submission.is_coordinator,
                'section': submission.section,
                'submission_date': submission.submission_date.isoformat() if submission.submission_date else None,
                'answer_count': answer_count
            })
        
        return JsonResponse(submissions_list, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

# Faculty Course Outline Structure API
@login_required
@require_http_methods(["GET"])
def api_faculty_course_outline_structure(request):
    """Outline starter structure: faculty coordinators or CRC (any course)."""
    if request.user.role not in (User.ROLE_FACULTY, User.ROLE_CRC_MEMBER):
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        course_id = request.GET.get('course_id')
        
        if not course_id:
            return JsonResponse({'error': 'course_id is required'}, status=400)
        
        if request.user.role == User.ROLE_FACULTY:
            try:
                CourseFaculty.objects.get(
                    faculty=request.user,
                    course_id=course_id,
                    is_coordinator=True
                )
            except CourseFaculty.DoesNotExist:
                return JsonResponse({
                    'error': 'Only course coordinators can create course outlines',
                    'has_access': False
                }, status=403)
        
        course = Course.objects.get(id=course_id)
        
        # Check for existing outline
        existing_outline = CourseOutline.objects.filter(
            course_id=course_id,
            faculty=request.user
        ).order_by('-version').first()
        
        # Default course outline structure
        default_structure = {
            "course_info": {
                "course_name": course.title,
                "course_code": course.code,
                "career_degree": "Undergraduate",
                "obe_enabled": True,
                "academic_term": "Jul 2025",
                "credits": course.credits,
                "department": course.department.name if course.department else ""
            },
            "sections": [
                {
                    "id": "course_information",
                    "title": "Course Information",
                    "type": "table",
                    "headers": ["Item", "Details"],
                    "rows": [
                        {"item": "Course Title", "details": course.title},
                        {"item": "Course Code", "details": course.code},
                        {"item": "Credit Hours", "details": str(course.credits)},
                        {"item": "Prerequisites", "details": ""},
                        {"item": "Corequisites", "details": ""}
                    ]
                },
                {
                    "id": "additional_info",
                    "title": "Additional Information",
                    "type": "text",
                    "content": "Enter additional course information here..."
                },
                {
                    "id": "calendar_activities",
                    "title": "Calendar of Activities",
                    "type": "table",
                    "headers": ["Week", "Topic", "Learning Outcomes", "Readings", "Assessment"],
                    "rows": []
                },
                {
                    "id": "course_books",
                    "title": "Course Books",
                    "type": "table",
                    "headers": ["Title", "Author", "Publisher", "Year", "ISBN"],
                    "rows": []
                },
                {
                    "id": "web_resources",
                    "title": "Web Resources",
                    "type": "list",
                    "items": []
                },
                {
                    "id": "assessment",
                    "title": "Assessment and Grading",
                    "type": "table",
                    "headers": ["Assessment Type", "Weight", "Due Date", "Description"],
                    "rows": []
                },
                {
                    "id": "learning_outcomes",
                    "title": "Course Learning Outcomes (CLOs)",
                    "type": "table",
                    "headers": ["CLO", "Description", "Bloom's Level", "Assessment Methods"],
                    "rows": []
                },
                {
                    "id": "grading_policy",
                    "title": "Grading Policy",
                    "type": "table",
                    "headers": ["Grade", "Range", "Points"],
                    "rows": [
                        {"grade": "A", "range": "90-100", "points": "4.0"},
                        {"grade": "B", "range": "80-89", "points": "3.0"},
                        {"grade": "C", "range": "70-79", "points": "2.0"},
                        {"grade": "D", "range": "60-69", "points": "1.0"},
                        {"grade": "F", "range": "Below 60", "points": "0.0"}
                    ]
                }
            ]
        }
        
        # If there's an existing outline, use its content
        if existing_outline and existing_outline.content:
            try:
                # Try to parse existing content as JSON
                existing_content = json.loads(existing_outline.content) if isinstance(existing_outline.content, str) else existing_outline.content
                
                # Merge with default structure
                if 'course_info' in existing_content:
                    default_structure['course_info'].update(existing_content['course_info'])
                
                if 'sections' in existing_content:
                    # Update sections from existing content
                    for existing_section in existing_content['sections']:
                        section_id = existing_section.get('id')
                        if section_id:
                            # Find and update the corresponding section in default structure
                            for i, default_section in enumerate(default_structure['sections']):
                                if default_section['id'] == section_id:
                                    default_structure['sections'][i].update(existing_section)
                                    break
            except:
                # If content is not valid JSON, use default structure
                pass
        
        return JsonResponse({
            'has_access': True,
            'template_available': False,
            'message': 'Course outlines are created directly',
            'structure': default_structure,
            'existing_outline': {
                'id': existing_outline.id if existing_outline else None,
                'version': existing_outline.version if existing_outline else 0,
                'title': existing_outline.title if existing_outline else '',
                'status': existing_outline.status if existing_outline else 'draft',
                'content': existing_outline.content if existing_outline else None
            } if existing_outline else None
        })
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_http_methods(["GET"])
def api_faculty_form_availability(request):
    """Check which forms are available for faculty for each course"""
    if request.user.role != User.ROLE_FACULTY:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        course_id = request.GET.get('course_id')
        
        # Check GLOBAL form availability
        ccr_active = DynamicForm.objects.filter(
            status=DynamicForm.STATUS_ACTIVE,
            form_type='ccr'
        ).exists()
        
        crr_active = DynamicForm.objects.filter(
            status=DynamicForm.STATUS_ACTIVE,
            form_type='crr'
        ).exists()
        
        if not course_id:
            # Return all courses with form availability
            course_assignments = CourseFaculty.objects.filter(
                faculty=request.user
            ).select_related('course', 'course__department')
            
            courses_data = []
            for assignment in course_assignments:
                courses_data.append({
                    'course_id': assignment.course.id,
                    'course_code': assignment.course.code,
                    'course_title': assignment.course.title,
                    'is_coordinator': assignment.is_coordinator,
                    'section': assignment.section,
                    'forms_available': {
                        'ccr': ccr_active and assignment.is_coordinator,
                        'crr': crr_active
                    }
                })
            
            return JsonResponse({
                'global_availability': {
                    'ccr': ccr_active,
                    'crr': crr_active
                },
                'courses': courses_data
            }, safe=False)
        else:
            # Check specific course
            try:
                assignment = CourseFaculty.objects.get(
                    faculty=request.user,
                    course_id=course_id
                )
                
                return JsonResponse({
                    'course_id': course_id,
                    'is_coordinator': assignment.is_coordinator,
                    'forms_available': {
                        'ccr': ccr_active and assignment.is_coordinator,
                        'crr': crr_active
                    }
                })
                
            except CourseFaculty.DoesNotExist:
                return JsonResponse({'error': 'Course not assigned to you'}, status=400)
                
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_get_all_outlines(request):
    """Get ALL outlines - both approved and submitted"""
    try:
        outlines = CourseOutline.objects.filter(
            status__in=['submitted', 'approved']
        ).select_related('course', 'faculty').order_by('-created_at')
        
        outlines_list = []
        for outline in outlines:
            outlines_list.append({
                'id': outline.id,
                'course_code': outline.course.code,
                'course_title': outline.course.title,
                'faculty': outline.faculty.username,
                'version': outline.version,
                'title': outline.title,
                'status': outline.status,
                'created_at': outline.created_at.strftime('%Y-%m-%d') if outline.created_at else None
            })
        
        return JsonResponse(outlines_list, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@user_passes_test(is_admin)
@csrf_exempt
@require_http_methods(["PUT"])
def api_department_update(request, department_id):
    try:
        data = json.loads(request.body)
        department = Department.objects.get(id=department_id)
        department.name = data.get('name', department.name)
        department.code = data.get('code', department.code)
        department.description = data.get('description', department.description)
        department.save()
        return JsonResponse({
            'id': department.id,
            'name': department.name,
            'code': department.code,
            'description': department.description
        })
    except Department.DoesNotExist:
        return JsonResponse({'error': 'Department not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# new apii

# Analysis Endpoints
@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_analysis_submissions_over_time(request):
    """Get form submissions over time (weekly periods).

    Always returns a contiguous timeline of the configured number of weeks so
    that the chart shows the full window even when most weeks have no data.
    Optional query params:
        - ``course_id``: restrict the chart to a single course.
        - ``weeks``: number of weeks of history to include (default 12, capped
          between 4 and 52).
    """
    try:
        selected_course_id = request.GET.get('course_id')
        try:
            weeks_window = int(request.GET.get('weeks', 12))
        except (TypeError, ValueError):
            weeks_window = 12
        weeks_window = max(4, min(weeks_window, 52))

        # Anchor the timeline on the Monday of the current week so each bucket
        # represents a full ISO week (Mon-Sun). Use timezone-aware "now" when
        # USE_TZ is enabled to avoid Django's naive-datetime warning.
        if getattr(settings, 'USE_TZ', False):
            from django.utils import timezone
            today = timezone.localtime(timezone.now())
        else:
            today = datetime.now()
        current_week_start = (today - timedelta(days=today.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        earliest_week_start = current_week_start - timedelta(weeks=weeks_window - 1)

        # Pre-seed every week in the window with zeroes so the chart always
        # renders a continuous x-axis instead of a single floating point.
        ordered_week_keys = []
        week_data = {}
        for week_offset in range(weeks_window):
            week_start = earliest_week_start + timedelta(weeks=week_offset)
            week_key = week_start.strftime('%Y-%m-%d')
            ordered_week_keys.append(week_key)
            week_data[week_key] = {'ccr': 0, 'crr': 0, 'total': 0}

        submissions = DynamicFormSubmission.objects.filter(
            submission_date__gte=earliest_week_start,
            dynamic_form__form_type__in=['ccr', 'crr'],
        ).select_related('dynamic_form').order_by('submission_date')

        if selected_course_id:
            submissions = submissions.filter(course_id=selected_course_id)

        for submission in submissions:
            submission_week_start = submission.submission_date - timedelta(
                days=submission.submission_date.weekday()
            )
            submission_week_start = submission_week_start.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            week_key = submission_week_start.strftime('%Y-%m-%d')
            # Submissions slightly older than the window can be safely ignored.
            bucket = week_data.get(week_key)
            if bucket is None:
                continue
            bucket['total'] += 1
            if submission.dynamic_form.form_type == 'ccr':
                bucket['ccr'] += 1
            else:
                bucket['crr'] += 1

        result = {
            'weeks': ordered_week_keys,
            'ccr_data': [week_data[week_key]['ccr'] for week_key in ordered_week_keys],
            'crr_data': [week_data[week_key]['crr'] for week_key in ordered_week_keys],
            'total_data': [week_data[week_key]['total'] for week_key in ordered_week_keys],
        }

        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_analysis_form_status(request):
    """Get form status distribution.

    Optional query param ``course_id`` restricts the chart to a single course.
    """
    try:
        selected_course_id = request.GET.get('course_id')

        # Get status counts for universal forms
        status_queryset = DynamicFormSubmission.objects.filter(
            dynamic_form__form_type__in=['ccr', 'crr']
        )

        if selected_course_id:
            status_queryset = status_queryset.filter(course_id=selected_course_id)

        status_counts = status_queryset.values('status').annotate(count=Count('id'))
        
        # Get totals
        total_submissions = sum(item['count'] for item in status_counts)
        
        # Format for pie chart
        result = {
            'labels': [],
            'data': [],
            'colors': []
        }
        
        status_colors = {
            'submitted': '#FFC107',  # Yellow
            'approved': '#4CAF50',    # Green
            'draft': '#9E9E9E',       # Grey
            'revision_requested': '#F44336',  # Red
        }
        
        for item in status_counts:
            result['labels'].append(item['status'].title())
            result['data'].append(item['count'])
            result['colors'].append(status_colors.get(item['status'], '#2196F3'))
        
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# Update the CLO achievement analysis function
@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_analysis_clo_achievement(request):
    """Get CLO achievement rates by analyzing actual form answers AND course outlines.

    Optional query param ``course_id`` restricts the analysis to a single course.
    """
    try:
        selected_course_id = request.GET.get('course_id')

        # Initialize CLO data for 4 CLOs
        clo_data = {
            'CLO1': {'scores': [], 'count': 0, 'achieved_count': 0, 'sources': []},
            'CLO2': {'scores': [], 'count': 0, 'achieved_count': 0, 'sources': []},
            'CLO3': {'scores': [], 'count': 0, 'achieved_count': 0, 'sources': []},
            'CLO4': {'scores': [], 'count': 0, 'achieved_count': 0, 'sources': []},
        }

        # PART 1: Analyze form submissions (CCR/CRR forms)
        submissions = DynamicFormSubmission.objects.filter(
            dynamic_form__form_type__in=['ccr', 'crr'],
            status__in=['submitted', 'approved']  # Only analyze submitted/approved forms
        ).prefetch_related('answers__question')

        if selected_course_id:
            submissions = submissions.filter(course_id=selected_course_id)
        
        form_count = 0
        for submission in submissions:
            answers = submission.answers.all()
            
            for answer in answers:
                question_text = answer.question.question_text.lower()
                
                # Method 1: Check for CLO percentage dictionary answers
                if isinstance(answer.answer_data, dict):
                    for clo_num in [1, 2, 3, 4]:
                        clo_key = f'CLO{clo_num}'
                        # Try different key formats
                        for key in [f'clo{clo_num}', f'clo_{clo_num}', f'CLO{clo_num}', f'CLO_{clo_num}']:
                            if key in answer.answer_data:
                                score = answer.answer_data[key]
                                if isinstance(score, (int, float)):
                                    clo_data[clo_key]['scores'].append(score)
                                    clo_data[clo_key]['count'] += 1
                                    clo_data[clo_key]['sources'].append(f"Form: {submission.course.code}")
                                    if score >= 70:
                                        clo_data[clo_key]['achieved_count'] += 1
                                elif isinstance(score, str):
                                    try:
                                        # Handle percentage strings
                                        if '%' in score:
                                            score_val = float(score.replace('%', '').strip())
                                        else:
                                            score_val = float(score)
                                        
                                        clo_data[clo_key]['scores'].append(score_val)
                                        clo_data[clo_key]['count'] += 1
                                        clo_data[clo_key]['sources'].append(f"Form: {submission.course.code}")
                                        if score_val >= 70:
                                            clo_data[clo_key]['achieved_count'] += 1
                                    except:
                                        pass
                
                # Method 2: Check question text for CLO references
                for clo_num in [1, 2, 3, 4]:
                    clo_patterns = [
                        f'clo{clo_num}',
                        f'clo {clo_num}',
                        f'course learning outcome {clo_num}',
                        f'learning outcome {clo_num}',
                        f'clo-{clo_num}',
                        f'clo_{clo_num}',
                    ]
                    
                    if any(pattern in question_text for pattern in clo_patterns):
                        clo_key = f'CLO{clo_num}'
                        
                        # Extract score from answer
                        score = extract_clo_score_from_answer(answer)
                        if score is not None:
                            clo_data[clo_key]['scores'].append(score)
                            clo_data[clo_key]['count'] += 1
                            clo_data[clo_key]['sources'].append(f"Form: {submission.course.code}")
                            
                            # Check if achieved (score >= 70%)
                            if score >= 70:
                                clo_data[clo_key]['achieved_count'] += 1
        
        # PART 2: Analyze course outlines for CLO data
        # Get approved course outlines
        approved_outlines = CourseOutline.objects.filter(
            status='approved',
            is_current=True
        )

        if selected_course_id:
            approved_outlines = approved_outlines.filter(course_id=selected_course_id)
        
        outline_count = 0
        for outline in approved_outlines:
            try:
                # Parse outline content (assuming JSON structure)
                if outline.content:
                    content = outline.content
                    if isinstance(content, str):
                        try:
                            content_data = json.loads(content)
                        except:
                            content_data = None
                    else:
                        content_data = content
                    
                    if content_data and isinstance(content_data, dict):
                        # Look for CLO data in outline structure
                        if 'sections' in content_data:
                            for section in content_data['sections']:
                                if isinstance(section, dict):
                                    # Check for CLO tables or sections
                                    section_title = section.get('title', '').lower()
                                    section_id = section.get('id', '').lower()
                                    
                                    # Check if this is a CLO-related section
                                    if any(clo_term in section_title or clo_term in section_id 
                                           for clo_term in ['clo', 'course learning outcome', 'learning outcome']):
                                        
                                        # Extract rows from table sections
                                        if section.get('type') == 'table' and 'rows' in section:
                                            for row in section['rows']:
                                                if isinstance(row, dict):
                                                    # Look for CLO data in row
                                                    row_text = str(row).lower()
                                                    for clo_num in [1, 2, 3, 4]:
                                                        if f'clo{clo_num}' in row_text or f'clo {clo_num}' in row_text:
                                                            clo_key = f'CLO{clo_num}'
                                                            
                                                            # Try to extract percentage from row
                                                            row_str = str(row)
                                                            import re
                                                            
                                                            # Look for percentages in row
                                                            percent_pattern = r'(\d+\.?\d*)%'
                                                            percentages = re.findall(percent_pattern, row_str)
                                                            if percentages:
                                                                try:
                                                                    score = float(percentages[0])
                                                                    clo_data[clo_key]['scores'].append(score)
                                                                    clo_data[clo_key]['count'] += 1
                                                                    clo_data[clo_key]['sources'].append(f"Outline: {outline.course.code}")
                                                                    if score >= 70:
                                                                        clo_data[clo_key]['achieved_count'] += 1
                                                                except:
                                                                    pass
            except Exception as e:
                print(f"Error parsing outline {outline.id}: {str(e)}")
                continue
        
        # Calculate achievement rates and prepare result
        result = {
            'clos': ['CLO1', 'CLO2', 'CLO3', 'CLO4'],
            'achievement_rates': [],
            'average_scores': [],
            'total_responses': [],
            'achieved_counts': [],
            'details': [],
            'sources_summary': {
                'form_submissions': form_count,
                'course_outlines': outline_count,
                'total_sources': form_count + outline_count
            }
        }
        
        for clo in result['clos']:
            scores = clo_data[clo]['scores']
            count = clo_data[clo]['count']
            achieved = clo_data[clo]['achieved_count']
            
            if count > 0:
                avg_score = sum(scores) / len(scores)
                achievement_rate = (achieved / count) * 100
            else:
                avg_score = 0
                achievement_rate = 0
            
            result['average_scores'].append(round(avg_score, 1))
            result['achievement_rates'].append(round(achievement_rate, 1))
            result['total_responses'].append(count)
            result['achieved_counts'].append(achieved)
            
            # Add detailed breakdown
            result['details'].append({
                'clo': clo,
                'average_score': round(avg_score, 1),
                'achievement_rate': round(achievement_rate, 1),
                'total_responses': count,
                'achieved_responses': achieved,
                'score_distribution': get_score_distribution(scores) if scores else {},
                'data_sources': list(set(clo_data[clo]['sources']))[:5]  # Unique sources, limit to 5
            })
        
        return JsonResponse(result)
    except Exception as e:
        print(f"Error in CLO achievement analysis: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=400)

def extract_clo_score_from_answer(answer):
    """Extract a numerical score (0-100) from an answer"""
    try:
        # If the question is CLO percentage type, check answer_data first
        if answer.question.question_type == 'clo_percentage' and answer.answer_data:
            if isinstance(answer.answer_data, dict):
                # For CLO percentage type, average all CLO values
                clo_values = []
                for clo_num in [1, 2, 3, 4]:
                    for key in [f'clo{clo_num}', f'clo_{clo_num}', f'CLO{clo_num}']:
                        if key in answer.answer_data:
                            value = answer.answer_data[key]
                            if isinstance(value, (int, float)):
                                clo_values.append(value)
                            elif isinstance(value, str):
                                try:
                                    if '%' in value:
                                        clo_values.append(float(value.replace('%', '').strip()))
                                    else:
                                        clo_values.append(float(value))
                                except:
                                    pass
                if clo_values:
                    return sum(clo_values) / len(clo_values)
                
                # Look for general score fields
                for key in ['score', 'percentage', 'rating', 'value', 'achievement']:
                    if key in answer.answer_data:
                        try:
                            value = answer.answer_data[key]
                            if isinstance(value, (int, float)):
                                return float(value)
                            elif isinstance(value, str):
                                if '%' in value:
                                    return float(value.replace('%', '').strip())
                                else:
                                    return float(value)
                        except:
                            continue
            
            # If it's a list, try to extract numeric values
            elif isinstance(answer.answer_data, list):
                numeric_values = []
                for item in answer.answer_data:
                    if isinstance(item, (int, float)):
                        numeric_values.append(item)
                    elif isinstance(item, str):
                        try:
                            # Try to convert to float
                            val = float(item)
                            numeric_values.append(val)
                        except:
                            # Try to extract number from string
                            import re
                            numbers = re.findall(r'\d+\.?\d*', item)
                            if numbers:
                                try:
                                    numeric_values.append(float(numbers[0]))
                                except:
                                    pass
                
                if numeric_values:
                    return sum(numeric_values) / len(numeric_values)
        
        # Case 4: Try to extract number from text
        if answer.answer_text:
            import re
            # Look for percentages first
            percent_pattern = r'(\d+\.?\d*)%'
            percent_matches = re.findall(percent_pattern, answer.answer_text)
            if percent_matches:
                try:
                    return float(percent_matches[0])
                except:
                    pass
            
            # Look for any numbers
            numbers = re.findall(r'\d+\.?\d*', answer.answer_text)
            if numbers:
                try:
                    # Take the first number that looks like a percentage (0-100)
                    for num in numbers:
                        val = float(num)
                        if 0 <= val <= 100:
                            return val
                    # If no number in 0-100 range, take the first one
                    return float(numbers[0])
                except:
                    pass
        
        # Case 5: Map textual answers to scores
        if answer.answer_text:
            text = answer.answer_text.lower().strip()
            
            # Check for percentage phrases
            if '100%' in text or 'hundred percent' in text:
                return 100
            elif '90%' in text or 'ninety percent' in text:
                return 90
            elif '80%' in text or 'eighty percent' in text:
                return 80
            elif '70%' in text or 'seventy percent' in text:
                return 70
            elif '60%' in text or 'sixty percent' in text:
                return 60
            elif '50%' in text or 'fifty percent' in text:
                return 50
            elif '40%' in text or 'forty percent' in text:
                return 40
            elif '30%' in text or 'thirty percent' in text:
                return 30
            elif '20%' in text or 'twenty percent' in text:
                return 20
            elif '10%' in text or 'ten percent' in text:
                return 10
            elif '0%' in text or 'zero percent' in text:
                return 0
            
            # Map textual ratings to scores
            mapping = {
                'excellent': 90, 'outstanding': 95, 'exceptional': 95,
                'very good': 85, 'very good': 85,
                'good': 80, 'well achieved': 80,
                'satisfactory': 75, 'adequate': 75, 'moderate': 75,
                'average': 70, 'medium': 70,
                'fair': 65, 'acceptable': 65,
                'poor': 60, 'below average': 60,
                'very poor': 50, 'inadequate': 50,
                'not achieved': 40, 'failed': 40, 'unsatisfactory': 40,
                'yes': 80, 'achieved': 80,
                'no': 40, 'not achieved': 40,
                'partially': 60, 'partially achieved': 60,
                'fully': 90, 'fully achieved': 90,
                'substantially': 85, 'mostly': 80,
            }
            
            for key, value in mapping.items():
                if key in text:
                    return value
            
            # Check for Likert scale
            likert_map = {
                '5': 90, '5/5': 90, '5 out of 5': 90, 'five': 90,
                '4': 75, '4/5': 75, '4 out of 5': 75, 'four': 75,
                '3': 60, '3/5': 60, '3 out of 5': 60, 'three': 60,
                '2': 45, '2/5': 45, '2 out of 5': 45, 'two': 45,
                '1': 30, '1/5': 30, '1 out of 5': 30, 'one': 30,
            }
            
            for key, value in likert_map.items():
                if key in text:
                    return value
        
        return None
    except:
        return None

def get_score_distribution(scores):
    """Get distribution of scores in categories"""
    if not scores:
        return {}
    
    distribution = {
        'Excellent (90-100)': 0,
        'Good (80-89)': 0,
        'Satisfactory (70-79)': 0,
        'Needs Improvement (60-69)': 0,
        'Poor (Below 60)': 0,
    }
    
    for score in scores:
        if score >= 90:
            distribution['Excellent (90-100)'] += 1
        elif score >= 80:
            distribution['Good (80-89)'] += 1
        elif score >= 70:
            distribution['Satisfactory (70-79)'] += 1
        elif score >= 60:
            distribution['Needs Improvement (60-69)'] += 1
        else:
            distribution['Poor (Below 60)'] += 1
    
    # Convert to percentages
    total = len(scores)
    if total > 0:
        for key in distribution:
            distribution[key] = round((distribution[key] / total) * 100, 1)
    
    return distribution

# Add this new endpoint for detailed CLO analysis
@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_analysis_detailed_clo(request, clo_number):
    """Get detailed analysis for a specific CLO"""
    try:
        if clo_number not in [1, 2, 3, 4]:
            return JsonResponse({'error': 'Invalid CLO number. Must be 1-4'}, status=400)
        
        clo_key = f'CLO{clo_number}'
        
        # Get all answers related to this CLO
        answers = FormAnswer.objects.filter(
            question__question_text__icontains=f'clo{clo_number}',
            submission__dynamic_form__form_type__in=['ccr', 'crr']
        ).select_related('submission', 'question', 'submission__course', 'submission__faculty')
        
        # Prepare detailed data
        detailed_data = []
        courses_data = {}
        faculty_data = {}
        
        for answer in answers:
            score = extract_clo_score_from_answer(answer)
            if score is None:
                continue
            
            # Course analysis
            course_code = answer.submission.course.code
            if course_code not in courses_data:
                courses_data[course_code] = {'scores': [], 'count': 0}
            courses_data[course_code]['scores'].append(score)
            courses_data[course_code]['count'] += 1
            
            # Faculty analysis
            faculty_name = answer.submission.faculty.username
            if faculty_name not in faculty_data:
                faculty_data[faculty_name] = {'scores': [], 'count': 0}
            faculty_data[faculty_name]['scores'].append(score)
            faculty_data[faculty_name]['count'] += 1
            
            # Add to detailed list
            detailed_data.append({
                'id': answer.id,
                'course_code': course_code,
                'course_title': answer.submission.course.title,
                'faculty': faculty_name,
                'question': answer.question.question_text[:100] + ('...' if len(answer.question.question_text) > 100 else ''),
                'answer': answer.answer_text[:200] if answer.answer_text else str(answer.answer_data)[:200],
                'score': score,
                'achieved': score >= 70,
                'submission_date': answer.submission.submission_date.isoformat() if answer.submission.submission_date else None,
                'form_type': answer.submission.dynamic_form.form_type,
            })
        
        # Calculate course averages
        course_analysis = []
        for course_code, data in courses_data.items():
            avg_score = sum(data['scores']) / len(data['scores'])
            achievement_rate = sum(1 for s in data['scores'] if s >= 70) / len(data['scores']) * 100
            course_analysis.append({
                'course_code': course_code,
                'average_score': round(avg_score, 1),
                'achievement_rate': round(achievement_rate, 1),
                'response_count': data['count']
            })
        
        # Calculate faculty averages
        faculty_analysis = []
        for faculty_name, data in faculty_data.items():
            avg_score = sum(data['scores']) / len(data['scores'])
            achievement_rate = sum(1 for s in data['scores'] if s >= 70) / len(data['scores']) * 100
            faculty_analysis.append({
                'faculty': faculty_name,
                'average_score': round(avg_score, 1),
                'achievement_rate': round(achievement_rate, 1),
                'response_count': data['count']
            })
        
        # Sort analyses
        course_analysis.sort(key=lambda x: x['achievement_rate'], reverse=True)
        faculty_analysis.sort(key=lambda x: x['achievement_rate'], reverse=True)
        
        # Calculate overall statistics
        all_scores = []
        for answer in detailed_data:
            all_scores.append(answer['score'])
        
        if all_scores:
            overall_avg = sum(all_scores) / len(all_scores)
            overall_achievement = sum(1 for s in all_scores if s >= 70) / len(all_scores) * 100
        else:
            overall_avg = 0
            overall_achievement = 0
        
        return JsonResponse({
            'clo': clo_key,
            'overall_statistics': {
                'average_score': round(overall_avg, 1),
                'achievement_rate': round(overall_achievement, 1),
                'total_responses': len(all_scores),
                'achieved_responses': sum(1 for s in all_scores if s >= 70),
                'score_range': {
                    'min': min(all_scores) if all_scores else 0,
                    'max': max(all_scores) if all_scores else 0,
                    'median': get_median(all_scores) if all_scores else 0
                }
            },
            'course_analysis': course_analysis,
            'faculty_analysis': faculty_analysis[:10],  # Top 10 faculty
            'detailed_responses': detailed_data[:50],  # Limit to 50 most recent
            'generated_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

def get_median(scores):
    """Calculate median of scores"""
    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    if n % 2 == 0:
        return (sorted_scores[n//2 - 1] + sorted_scores[n//2]) / 2
    else:
        return sorted_scores[n//2]

# Add endpoint for trend analysis
@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_analysis_clo_trends(request):
    """Get CLO achievement trends over time"""
    try:
        # Get data for last 4 quarters
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)  # Last year
        
        # Initialize data structure
        quarters = []
        clo_trends = {
            'CLO1': [],
            'CLO2': [],
            'CLO3': [],
            'CLO4': []
        }
        
        # Divide into quarters
        for i in range(4):
            quarter_start = start_date + timedelta(days=i*90)
            quarter_end = start_date + timedelta(days=(i+1)*90)
            quarter_name = f"Q{i+1} {quarter_start.year}"
            quarters.append(quarter_name)
            
            # Get answers for this quarter
            for clo_num in [1, 2, 3, 4]:
                answers = FormAnswer.objects.filter(
                    question__question_text__icontains=f'clo{clo_num}',
                    submission__submission_date__gte=quarter_start,
                    submission__submission_date__lt=quarter_end,
                    submission__dynamic_form__form_type__in=['ccr', 'crr']
                )
                
                scores = []
                for answer in answers:
                    score = extract_clo_score_from_answer(answer)
                    if score is not None:
                        scores.append(score)
                
                if scores:
                    achievement_rate = sum(1 for s in scores if s >= 70) / len(scores) * 100
                else:
                    achievement_rate = 0
                
                clo_trends[f'CLO{clo_num}'].append(round(achievement_rate, 1))
        
        return JsonResponse({
            'quarters': quarters,
            'trends': clo_trends,
            'time_period': f"{start_date.strftime('%b %Y')} - {end_date.strftime('%b %Y')}"
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["POST"])
def api_compare_outlines(request):
    """Compare two course outline versions using an LLM.

    The configured AI provider (via LiteLLM) is used to produce a rich
    qualitative comparison: an executive summary, a similarity score, the
    added / modified / removed sections with natural-language explanations,
    and improvement recommendations.

    When the AI is unavailable (no API key, network error, malformed
    response, ...) the function falls back to the structural diff helpers
    so the UI keeps working.
    """
    try:
        data = json.loads(request.body)
        outline1_id = data.get('outline1_id')
        outline2_id = data.get('outline2_id')

        if not outline1_id or not outline2_id:
            return JsonResponse({'error': 'Both outline IDs are required'}, status=400)

        first_outline = CourseOutline.objects.select_related('course', 'faculty').get(id=outline1_id)
        second_outline = CourseOutline.objects.select_related('course', 'faculty').get(id=outline2_id)

        if first_outline.course_id != second_outline.course_id:
            return JsonResponse({'error': 'Outlines must be from the same course'}, status=400)

        parsed_first_content = _parse_outline_content(first_outline.content)
        parsed_second_content = _parse_outline_content(second_outline.content)

        outline_meta = {
            'outline1': _serialize_outline_meta(first_outline),
            'outline2': _serialize_outline_meta(second_outline),
            'course': {
                'code': first_outline.course.code,
                'title': first_outline.course.title,
            },
            'compared_at': datetime.now().isoformat(),
        }

        ai_config = get_ai_provider_config()
        ai_payload = None
        ai_error_message = None

        if ai_config.get('available'):
            try:
                ai_payload = _generate_ai_outline_comparison(
                    first_outline,
                    second_outline,
                    parsed_first_content,
                    parsed_second_content,
                    ai_config,
                )
            except Exception as ai_exc:
                ai_error_message = str(ai_exc)
                print(f"AI outline comparison failed: {ai_error_message}")
        else:
            ai_error_message = (
                f"AI provider '{ai_config.get('provider', 'unknown')}' is not configured."
            )

        fallback_differences = _build_fallback_differences(
            parsed_first_content,
            parsed_second_content,
        )

        if ai_payload is not None:
            response_body = {
                **outline_meta,
                'comparison_mode': 'ai',
                'ai_provider': ai_config.get('provider'),
                'ai_model': ai_config.get('model'),
                'ai': ai_payload,
                'differences': fallback_differences,
            }
        else:
            response_body = {
                **outline_meta,
                'comparison_mode': 'fallback',
                'ai_provider': ai_config.get('provider'),
                'ai_model': ai_config.get('model'),
                'ai_unavailable_reason': ai_error_message,
                'differences': fallback_differences,
            }

        return JsonResponse(response_body)

    except CourseOutline.DoesNotExist:
        return JsonResponse({'error': 'Outline not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def _serialize_outline_meta(outline):
    return {
        'id': outline.id,
        'version': outline.version,
        'title': outline.title,
        'status': outline.status,
        'is_current': outline.is_current,
        'faculty': outline.faculty.username if outline.faculty_id else '',
        'created_at': outline.created_at.isoformat() if outline.created_at else None,
        'updated_at': outline.updated_at.isoformat() if outline.updated_at else None,
        'submitted_at': outline.submitted_at.isoformat() if outline.submitted_at else None,
        'approved_at': outline.approved_at.isoformat() if outline.approved_at else None,
    }


def _parse_outline_content(raw_content):
    """Return outline content as a dict if it looks like JSON, otherwise as text."""
    if raw_content in (None, ''):
        return ''
    if isinstance(raw_content, dict) or isinstance(raw_content, list):
        return raw_content
    if isinstance(raw_content, str):
        candidate = raw_content.strip()
        if candidate.startswith('{') or candidate.startswith('['):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                return raw_content
        return raw_content
    return str(raw_content)


def _build_fallback_differences(parsed_first_content, parsed_second_content):
    """Always compute structural/textual diffs so we have data even without AI."""
    try:
        if isinstance(parsed_first_content, dict) and isinstance(parsed_second_content, dict):
            return compare_structured_content(parsed_first_content, parsed_second_content)
        first_text = parsed_first_content if isinstance(parsed_first_content, str) else json.dumps(parsed_first_content, indent=2)
        second_text = parsed_second_content if isinstance(parsed_second_content, str) else json.dumps(parsed_second_content, indent=2)
        return compare_text_content(first_text, second_text)
    except Exception as exc:
        print(f"Fallback diff failed: {exc}")
        return {'added': [], 'modified': [], 'deleted': []}


def _build_outline_excerpt_for_ai(parsed_content, character_limit=8000):
    """Format outline content for inclusion in the LLM prompt with a length cap."""
    if isinstance(parsed_content, (dict, list)):
        try:
            text = json.dumps(parsed_content, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(parsed_content)
    else:
        text = str(parsed_content or '')

    if len(text) > character_limit:
        return text[:character_limit] + "\n... [truncated] ..."
    return text


def _extract_json_from_ai_response(raw_text):
    """Extract the first valid JSON object from a LLM response.

    LLMs occasionally wrap JSON in markdown fences or add commentary. This
    helper tolerates both.
    """
    if raw_text is None:
        raise ValueError("Empty AI response")

    text = raw_text.strip()
    if not text:
        raise ValueError("Empty AI response")

    fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
    if fence_match:
        return json.loads(fence_match.group(1))

    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace:last_brace + 1]
        return json.loads(candidate)

    return json.loads(text)


def _normalize_ai_comparison_payload(payload):
    """Coerce the AI response into the shape the frontend expects."""
    if not isinstance(payload, dict):
        raise ValueError("AI response is not a JSON object")

    def _coerce_string(value, default=""):
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def _coerce_list_of_dicts(items, required_keys):
        normalized_items = []
        if not isinstance(items, list):
            return normalized_items
        for entry in items:
            if not isinstance(entry, dict):
                continue
            normalized_entry = {}
            for required_key in required_keys:
                normalized_entry[required_key] = _coerce_string(entry.get(required_key, ""))
            optional_severity = entry.get('severity') or entry.get('impact')
            if optional_severity:
                normalized_entry['severity'] = _coerce_string(optional_severity)
            normalized_items.append(normalized_entry)
        return normalized_items

    try:
        similarity_value = float(payload.get('similarity_score', 0))
    except (TypeError, ValueError):
        similarity_value = 0.0
    similarity_value = max(0.0, min(100.0, similarity_value))

    overall_change_level = _coerce_string(
        payload.get('overall_change_level') or payload.get('change_level') or 'moderate'
    ).lower()
    if overall_change_level not in {'minimal', 'minor', 'moderate', 'major', 'significant'}:
        overall_change_level = 'moderate'

    key_themes = payload.get('key_themes') or payload.get('themes') or []
    if not isinstance(key_themes, list):
        key_themes = [key_themes]
    key_themes = [_coerce_string(theme) for theme in key_themes if theme]

    recommendations = payload.get('recommendations') or []
    if not isinstance(recommendations, list):
        recommendations = [recommendations]
    recommendations = [_coerce_string(item) for item in recommendations if item]

    return {
        'summary': _coerce_string(payload.get('summary'), default=""),
        'similarity_score': round(similarity_value, 1),
        'overall_change_level': overall_change_level,
        'key_themes': key_themes,
        'added_sections': _coerce_list_of_dicts(
            payload.get('added_sections') or payload.get('added') or [],
            ['title', 'description'],
        ),
        'removed_sections': _coerce_list_of_dicts(
            payload.get('removed_sections') or payload.get('deleted') or payload.get('removed') or [],
            ['title', 'description'],
        ),
        'modified_sections': _coerce_list_of_dicts(
            payload.get('modified_sections') or payload.get('modified') or payload.get('changed') or [],
            ['title', 'description', 'old_summary', 'new_summary'],
        ),
        'recommendations': recommendations,
    }


def _generate_ai_outline_comparison(
    first_outline,
    second_outline,
    parsed_first_content,
    parsed_second_content,
    ai_config,
):
    """Call the LLM to produce a structured comparison of two outlines."""
    first_excerpt = _build_outline_excerpt_for_ai(parsed_first_content)
    second_excerpt = _build_outline_excerpt_for_ai(parsed_second_content)

    prompt = (
        "You are an expert academic curriculum reviewer comparing two versions of a "
        "course outline. Produce a precise, professional analysis.\n\n"
        f"Course: {first_outline.course.code} - {first_outline.course.title}\n\n"
        "=== OUTLINE A (older / left side) ===\n"
        f"Version: {first_outline.version}\n"
        f"Title: {first_outline.title}\n"
        f"Status: {first_outline.status}\n"
        f"Author: {first_outline.faculty.username if first_outline.faculty_id else 'Unknown'}\n"
        "Content:\n"
        f"{first_excerpt}\n\n"
        "=== OUTLINE B (newer / right side) ===\n"
        f"Version: {second_outline.version}\n"
        f"Title: {second_outline.title}\n"
        f"Status: {second_outline.status}\n"
        f"Author: {second_outline.faculty.username if second_outline.faculty_id else 'Unknown'}\n"
        "Content:\n"
        f"{second_excerpt}\n\n"
        "Compare Outline B against Outline A and respond with ONLY valid JSON, no "
        "Markdown fences, with the following shape:\n"
        "{\n"
        '  "summary": "2-4 sentence executive summary of how Outline B differs from Outline A",\n'
        '  "similarity_score": 0-100 (higher means more similar),\n'
        '  "overall_change_level": "minimal" | "minor" | "moderate" | "major",\n'
        '  "key_themes": ["short bullet phrases of the main themes of change"],\n'
        '  "added_sections": [ { "title": "...", "description": "what was added and why it matters", "severity": "low|medium|high" } ],\n'
        '  "removed_sections": [ { "title": "...", "description": "what was removed and the impact", "severity": "low|medium|high" } ],\n'
        '  "modified_sections": [ { "title": "...", "description": "nature of the change", "old_summary": "what Outline A said", "new_summary": "what Outline B says", "severity": "low|medium|high" } ],\n'
        '  "recommendations": ["actionable improvement recommendations for the new outline"]\n'
        "}\n"
        "Focus on pedagogically meaningful differences (CLOs, assessment weighting, "
        "topics, contact hours, references). Ignore trivial formatting/whitespace changes. "
        "If a category has no items, return an empty list. Keep descriptions concise "
        "(<= 2 sentences). Output only the JSON object."
    )

    raw_response = call_llm_api(prompt, ai_config)
    parsed_response = _extract_json_from_ai_response(raw_response)
    normalized_response = _normalize_ai_comparison_payload(parsed_response)
    return normalized_response

def compare_structured_content(content1, content2):
    """Compare two structured JSON contents"""
    differences = {
        'added': [],
        'modified': [],
        'deleted': []
    }
    
    # Compare sections if they exist
    if 'sections' in content1 and 'sections' in content2:
        sections1 = {section.get('id', str(i)): section for i, section in enumerate(content1['sections'])}
        sections2 = {section.get('id', str(i)): section for i, section in enumerate(content2['sections'])}
        
        # Find added sections
        for section_id, section in sections2.items():
            if section_id not in sections1:
                differences['added'].append({
                    'id': section_id,
                    'title': section.get('title', 'Untitled Section'),
                    'content': section
                })
        
        # Find deleted sections
        for section_id, section in sections1.items():
            if section_id not in sections2:
                differences['deleted'].append({
                    'id': section_id,
                    'title': section.get('title', 'Untitled Section'),
                    'content': section
                })
        
        # Find modified sections
        for section_id in set(sections1.keys()) & set(sections2.keys()):
            if sections1[section_id] != sections2[section_id]:
                differences['modified'].append({
                    'id': section_id,
                    'title': sections2[section_id].get('title', 'Untitled Section'),
                    'old_content': sections1[section_id],
                    'new_content': sections2[section_id]
                })
    
    return differences

def compare_text_content(text1, text2):
    """Compare two text contents"""
    lines1 = text1.split('\n')
    lines2 = text2.split('\n')
    
    differences = {
        'added': [],
        'modified': [],
        'deleted': []
    }
    
    # Simple line-by-line comparison
    for i, (line1, line2) in enumerate(itertools.zip_longest(lines1, lines2, fillvalue="")):
        if i >= len(lines1):
            # Line added in version 2
            if line2.strip():
                differences['added'].append({
                    'line': i + 1,
                    'content': line2
                })
        elif i >= len(lines2):
            # Line deleted in version 2
            if line1.strip():
                differences['deleted'].append({
                    'line': i + 1,
                    'content': line1
                })
        elif line1 != line2:
            # Line modified
            differences['modified'].append({
                'line': i + 1,
                'old_content': line1,
                'new_content': line2
            })
    
    return differences

@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_analysis_course_submissions(request):
    """Return CCR/CRR submissions for a single course along with all answers.

    This powers the per-course detail panel on the Analysis Dashboard so the
    CRC member can drill into every dynamically created form submission for
    the selected course.
    """
    try:
        selected_course_id = request.GET.get('course_id')
        if not selected_course_id:
            return JsonResponse({'error': 'course_id is required'}, status=400)

        try:
            course = Course.objects.select_related('department').get(id=selected_course_id)
        except Course.DoesNotExist:
            return JsonResponse({'error': 'Course not found'}, status=404)

        submissions = DynamicFormSubmission.objects.filter(
            course_id=selected_course_id,
            dynamic_form__form_type__in=['ccr', 'crr'],
        ).select_related(
            'faculty', 'dynamic_form'
        ).prefetch_related('answers__question').order_by('-submission_date')

        ccr_count = 0
        crr_count = 0
        approved_count = 0
        submitted_count = 0
        draft_count = 0
        revision_count = 0

        submissions_payload = []
        for submission in submissions:
            form_type = submission.dynamic_form.form_type
            if form_type == 'ccr':
                ccr_count += 1
            elif form_type == 'crr':
                crr_count += 1

            if submission.status == 'approved':
                approved_count += 1
            elif submission.status == 'submitted':
                submitted_count += 1
            elif submission.status == 'draft':
                draft_count += 1
            elif submission.status == 'revision_requested':
                revision_count += 1

            answers_payload = []
            for answer in submission.answers.all():
                answers_payload.append({
                    'question_id': answer.question.id,
                    'question_text': answer.question.question_text,
                    'question_type': answer.question.question_type,
                    'order': answer.question.order,
                    'answer_text': answer.answer_text,
                    'answer_data': answer.answer_data,
                    'has_file': bool(answer.file_upload),
                    'file_url': answer.file_upload.url if answer.file_upload else None,
                })

            answers_payload.sort(key=lambda item: item.get('order') or 0)

            submissions_payload.append({
                'submission_id': submission.id,
                'form_id': submission.dynamic_form.id,
                'form_name': submission.dynamic_form.name,
                'form_type': form_type,
                'form_type_label': submission.dynamic_form.get_form_type_display(),
                'faculty_username': submission.faculty.username,
                'faculty_email': submission.faculty.email,
                'faculty_department': submission.faculty.department,
                'is_coordinator': submission.is_coordinator,
                'section': submission.section,
                'status': submission.status,
                'status_label': submission.get_status_display(),
                'submission_date': submission.submission_date.isoformat() if submission.submission_date else None,
                'updated_at': submission.updated_at.isoformat() if submission.updated_at else None,
                'answers': answers_payload,
            })

        total_submissions = len(submissions_payload)
        approval_rate = round((approved_count / total_submissions) * 100, 1) if total_submissions else 0

        return JsonResponse({
            'course': {
                'id': course.id,
                'code': course.code,
                'title': course.title,
                'description': course.description,
                'credits': course.credits,
                'department': course.department.name if course.department else '',
            },
            'summary': {
                'total_submissions': total_submissions,
                'ccr_submissions': ccr_count,
                'crr_submissions': crr_count,
                'approved': approved_count,
                'submitted': submitted_count,
                'draft': draft_count,
                'revision_requested': revision_count,
                'approval_rate': approval_rate,
            },
            'submissions': submissions_payload,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_analysis_clo_by_course(request):
    """Get CLO achievement data broken down by course"""
    try:
        courses = Course.objects.all()
        course_clo_data = []
        
        for course in courses:
            course_data = {
                'course_id': course.id,
                'course_code': course.code,
                'course_title': course.title,
                'department': course.department.name if course.department else '',
                'clo_data': {
                    'CLO1': {'scores': [], 'count': 0, 'achieved': 0},
                    'CLO2': {'scores': [], 'count': 0, 'achieved': 0},
                    'CLO3': {'scores': [], 'count': 0, 'achieved': 0},
                    'CLO4': {'scores': [], 'count': 0, 'achieved': 0},
                }
            }
            
            # Get form submissions for this course
            submissions = DynamicFormSubmission.objects.filter(
                course=course,
                dynamic_form__form_type__in=['ccr', 'crr'],
                status__in=['submitted', 'approved']
            ).prefetch_related('answers__question')
            
            for submission in submissions:
                answers = submission.answers.all()
                
                for answer in answers:
                    # Check for CLO percentage dictionary
                    if isinstance(answer.answer_data, dict):
                        for clo_num in [1, 2, 3, 4]:
                            clo_key = f'CLO{clo_num}'
                            for key in [f'clo{clo_num}', f'clo_{clo_num}', f'CLO{clo_num}']:
                                if key in answer.answer_data:
                                    score = answer.answer_data[key]
                                    if isinstance(score, (int, float)):
                                        course_data['clo_data'][clo_key]['scores'].append(score)
                                        course_data['clo_data'][clo_key]['count'] += 1
                                        if score >= 70:
                                            course_data['clo_data'][clo_key]['achieved'] += 1
                                    elif isinstance(score, str):
                                        try:
                                            if '%' in score:
                                                score_val = float(score.replace('%', '').strip())
                                            else:
                                                score_val = float(score)
                                            
                                            course_data['clo_data'][clo_key]['scores'].append(score_val)
                                            course_data['clo_data'][clo_key]['count'] += 1
                                            if score_val >= 70:
                                                course_data['clo_data'][clo_key]['achieved'] += 1
                                        except:
                                            pass
            
            # Calculate averages and rates for this course
            for clo in ['CLO1', 'CLO2', 'CLO3', 'CLO4']:
                scores = course_data['clo_data'][clo]['scores']
                count = course_data['clo_data'][clo]['count']
                achieved = course_data['clo_data'][clo]['achieved']
                
                if count > 0:
                    avg_score = sum(scores) / len(scores)
                    achievement_rate = (achieved / count) * 100
                else:
                    avg_score = 0
                    achievement_rate = 0
                
                course_data['clo_data'][clo]['average_score'] = round(avg_score, 1)
                course_data['clo_data'][clo]['achievement_rate'] = round(achievement_rate, 1)
            
            course_clo_data.append(course_data)
        
        return JsonResponse(course_clo_data, safe=False)
        
    except Exception as e:
        print(f"Error in CLO by course analysis: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)



def get_ai_provider_config():
    """Get AI provider configuration from settings"""
    return {
        'provider': settings.AI_CONFIG.get('provider', 'openai'),
        'model': settings.AI_CONFIG.get('model', 'gpt-4'),
        'api_key': settings.AI_CONFIG.get('api_key'),
        'api_base': settings.AI_CONFIG.get('api_base'),
        'available': bool(settings.AI_CONFIG.get('api_key')),
        'timeout': 30.0,
        'max_tokens': 4000,
        'temperature': 0.3
    }

def get_model_string(provider, model_name):
    """Convert provider and model name to LiteLLM compatible string"""
    provider_mappings = {
        'openai': model_name,  # gpt-4, gpt-3.5-turbo, etc.
        'openrouter': f'openrouter/{model_name}',
        'deepseek': f'deepseek/{model_name}',
        'anthropic': f'claude-{model_name}',
        'groq': f'groq/{model_name}',
        'ollama': model_name,
        'together': f'together_ai/{model_name}',
        'huggingface': f'huggingface/{model_name}',
    }
    
    # Return the mapping or default to model_name
    return provider_mappings.get(provider, model_name)

def call_llm_api(prompt, config=None):
    """Generic function to call any LLM provider via LiteLLM"""
    if config is None:
        config = get_ai_provider_config()
    
    if not config['available']:
        raise Exception(f"AI API key not configured for provider: {config['provider']}")
    
    try:
        # Construct model string
        model_string = get_model_string(config['provider'], config['model'])
        
        # Call the API via LiteLLM
        response = litellm.completion(
            model=model_string,
            messages=[
                {"role": "system", "content": "You are an expert CQI analyst for higher education institutions."},
                {"role": "user", "content": prompt}
            ],
            api_key=config['api_key'],
            api_base=config.get('api_base'),
            temperature=config.get('temperature', 0.3),
            max_tokens=config.get('max_tokens', 4000),
            timeout=config.get('timeout', 30.0)
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"AI API Error ({config['provider']}): {str(e)}")
        raise Exception(f"AI service error ({config['provider']}): {str(e)}")



#  CQI report function 
@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["POST"])
def api_generate_cqi_report(request):
    """Generate CQI report using any AI provider via LiteLLM"""
    try:
        data = json.loads(request.body)
        course_id = data.get('course_id')
        time_period = data.get('time_period', 'quarter')
        report_type = data.get('report_type', 'summary')
        
        print(f"CQI Report Request: course_id={course_id}, time_period={time_period}, report_type={report_type}")
        
        # Check if AI is configured
        ai_config = get_ai_provider_config()
        if not ai_config['available']:
            return JsonResponse({
                'error': 'AI service not configured. Please set AI_API_KEY in environment variables.',
                'success': False,
                'fallback_report': "CQI Report Generation Failed: AI service not configured."
            }, status=400)
        
        # Collect comprehensive data for AI analysis
        context_data = collect_data_for_ai(course_id, time_period)
        
        # Add metadata to context
        context_data['metadata'] = {
            'course_id': course_id,
            'time_period': time_period,
            'report_type': report_type,
            'generated_at': datetime.now().isoformat(),
            'ai_provider': ai_config['provider'],
            'ai_model': ai_config['model'],
            'data_summary': {
                'form_submissions_count': len(context_data.get('form_submissions', [])),
                'course_outlines_count': len(context_data.get('course_outlines', [])),
                'has_clo_data': bool(context_data.get('clo_analysis', {}))
            }
        }
        
        # Generate report using AI
        try:
            report = generate_ai_report(context_data, report_type, ai_config)
            
            return JsonResponse({
                'report': report,
                'generated_at': datetime.now().isoformat(),
                'course_id': course_id,
                'time_period': time_period,
                'report_type': report_type,
                'ai_provider': ai_config['provider'],
                'ai_model': ai_config['model'],
                'context_summary': {
                    'form_submissions_analyzed': len(context_data.get('form_submissions', [])),
                    'course_outlines_analyzed': len(context_data.get('course_outlines', [])),
                    'clo_analysis_included': bool(context_data.get('clo_analysis', {})),
                    'statistics': context_data.get('statistics', {})
                },
                'success': True
            })
        except Exception as ai_error:
            print(f"AI generation error: {ai_error}")
            # Fallback to manual report
            fallback_report = generate_fallback_report(context_data, report_type)
            return JsonResponse({
                'report': fallback_report,
                'generated_at': datetime.now().isoformat(),
                'course_id': course_id,
                'time_period': time_period,
                'report_type': report_type,
                'note': f'Generated using fallback method due to AI error: {str(ai_error)}',
                'success': False,
                'error': str(ai_error)
            })
        
    except Exception as e:
        print(f"Error in CQI report generation: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error': str(e),
            'message': 'Failed to generate report. Please try again.',
            'success': False,
            'fallback_report': f"CQI Report Generation Failed\n\nError: {str(e)}"
        }, status=400)



def generate_ai_report(context_data, report_type="summary", ai_config=None):
    """Generate report using any AI provider"""
    if ai_config is None:
        ai_config = get_ai_provider_config()
    
    # Create prompt based on report type
    if report_type == "summary":
        sections = """
        1. Executive Summary (2-3 paragraphs)
        2. Key Findings (Bulleted list of 5-7 key points)
        3. Recommendations for Improvement (3-5 actionable recommendations)
        """
    elif report_type == "detailed":
        sections = """
        1. Executive Summary
        2. Key Findings and Analysis
        3. Submissions Analysis (CCR vs CRR forms comparison)
        4. Course Outline Quality Assessment
        5. Faculty Engagement Analysis
        6. CLO Achievement Analysis
        7. Recommendations for Improvement
        8. Action Items and Timeline
        """
    elif report_type == "recommendations":
        sections = """
        1. Key Recommendations (Prioritized list)
        2. Implementation Strategy
        3. Expected Outcomes
        4. Timeline and Resources Required
        """
    else:
        sections = """
        1. Executive Summary
        2. Key Findings
        3. Recommendations for Improvement
        4. Action Items
        """
    
    # Create the prompt
    prompt = f"""
    ROLE: You are a CQI (Continuous Quality Improvement) analyst for an academic institution.
    
    TASK: Analyze the following academic data and generate a comprehensive CQI report.
    
    REPORT TYPE: {report_type.upper()}
    
    AI CONFIGURATION:
    - Provider: {ai_config['provider']}
    - Model: {ai_config['model']}
    
    DATA TO ANALYZE:
    {json.dumps(context_data, indent=2)}
    
    REPORT STRUCTURE:
    {sections}
    
    REPORT REQUIREMENTS:
    1. Be specific, actionable, and evidence-based
    2. Use academic and professional language
    3. Include quantitative data from the provided statistics
    4. Provide clear recommendations with implementation steps
    5. Consider institutional constraints and practical feasibility
    6. Highlight both strengths and areas for improvement
    7. Include metrics and KPIs where relevant
    
    FORMATTING:
    - Use clear headings and subheadings
    - Use bullet points for lists
    - Keep paragraphs concise (3-5 sentences)
    
    TONE: Professional, analytical, constructive, and solution-oriented
    
    IMPORTANT: Base all analysis ONLY on the provided data. Do not fabricate or assume data not present.
    """
    
    print(f"Generating {report_type} report with {ai_config['provider']} ({ai_config['model']})...")
    
    # Call the generic LLM function
    return call_llm_api(prompt, ai_config)

def generate_fallback_report(context_data, report_type):
    """Generate a manual fallback report if AI fails"""
    stats = context_data.get('statistics', {})
    course = context_data.get('course', {})
    
    base_report = f"""
    CQI REPORT - MANUAL GENERATION
    
    Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
    Report Type: {report_type.upper()}
    
    """
    
    if course:
        base_report += f"Course: {course.get('code', 'N/A')} - {course.get('title', 'N/A')}\n"
        base_report += f"Department: {course.get('department', 'N/A')}\n\n"
    
    if report_type == "summary":
        return base_report + f"""
    Executive Summary:
    This report analyzes quality metrics based on {stats.get('total_submissions', 0)} form submissions 
    and {len(context_data.get('outlines', []))} course outlines.
    
    Key Findings:
    1. Total submissions: {stats.get('total_submissions', 0)}
    2. Approved submissions: {stats.get('approved_submissions', 0)} ({stats.get('total_submissions', 1) and (stats.get('approved_submissions', 0)/stats.get('total_submissions', 1))*100:.1f}%)
    3. Pending review: {stats.get('pending_submissions', 0)}
    4. Revision requests: {stats.get('revision_requests', 0)}
    
    Recommendations:
    1. Review submission processes for efficiency
    2. Provide faculty training on form completion
    3. Implement regular quality checks
    """
    elif report_type == "detailed":
        return base_report + f"""
    DETAILED ANALYSIS REPORT
    
    Statistics Overview:
    - Total Submissions: {stats.get('total_submissions', 0)}
    - Approved: {stats.get('approved_submissions', 0)}
    - Pending: {stats.get('pending_submissions', 0)}
    - Revision Requests: {stats.get('revision_requests', 0)}
    
    Data Sources:
    - Course Outlines: {len(context_data.get('outlines', []))}
    - Recent Submissions: {len(context_data.get('submissions', []))}
    
    Analysis:
    1. Submission patterns show consistent faculty engagement
    2. Approval rates indicate quality of submissions
    3. Revision requests highlight areas for improvement
    
    Action Items:
    1. Schedule faculty training sessions
    2. Review and update submission guidelines
    3. Implement automated quality checks
    """
    else:  # recommendations
        return base_report + f"""
    RECOMMENDATIONS REPORT
    
    Based on analysis of {stats.get('total_submissions', 0)} submissions:
    
    1. PRIORITY RECOMMENDATIONS:
       - Implement submission quality checklist
       - Provide faculty feedback within 48 hours
       - Standardize evaluation criteria
    
    2. MEDIUM-TERM ACTIONS:
       - Develop training modules
       - Create submission templates
       - Establish quality benchmarks
    
    3. LONG-TERM GOALS:
       - Automate quality assessment
       - Integrate with learning management system
       - Establish continuous improvement cycle
    """



def collect_data_for_ai(course_id, time_period):
    """Collect data for AI analysis"""
    data = {}
    
    # Get course information
    if course_id:
        try:
            course = Course.objects.get(id=course_id)
            data['course'] = {
                'code': course.code,
                'title': course.title,
                'department': course.department.name if course.department else None,
                'credits': course.credits
            }
            
            # Get course outlines
            outlines = CourseOutline.objects.filter(course=course).order_by('-version')
            data['outlines'] = []
            for outline in outlines[:5]:  # Last 5 versions
                data['outlines'].append({
                    'version': outline.version,
                    'status': outline.status,
                    'title': outline.title,
                    'created_at': outline.created_at.isoformat() if outline.created_at else None,
                    'notes': outline.notes
                })
        except Course.DoesNotExist:
            pass
    
    # Get form submissions - CREATE THE BASE QUERYSET
    if course_id:
        submissions_qs = DynamicFormSubmission.objects.filter(
            course_id=course_id,
            dynamic_form__form_type__in=['ccr', 'crr']
        ).select_related('faculty', 'dynamic_form')
    else:
        submissions_qs = DynamicFormSubmission.objects.filter(
            dynamic_form__form_type__in=['ccr', 'crr']
        ).select_related('faculty', 'dynamic_form', 'course')
    
    # Apply time filter - CREATE A NEW QUERYSET FOR FILTERING
    filtered_submissions = submissions_qs
    if time_period != 'all':
        if time_period == 'week':
            start_date = datetime.now() - timedelta(days=7)
        elif time_period == 'month':
            start_date = datetime.now() - timedelta(days=30)
        elif time_period == 'quarter':
            start_date = datetime.now() - timedelta(days=90)
        else:
            start_date = datetime.now() - timedelta(days=7)  # Default to week
        
        filtered_submissions = submissions_qs.filter(submission_date__gte=start_date)
    
    # Calculate statistics FIRST (before slicing)
    data['statistics'] = {
        'total_submissions': filtered_submissions.count(),
        'approved_submissions': filtered_submissions.filter(status='approved').count(),
        'pending_submissions': filtered_submissions.filter(status='submitted').count(),
        'revision_requests': filtered_submissions.filter(status='revision_requested').count()
    }
    
    # Now get submission data (slice after calculations)
    data['submissions'] = []
    # Use list() to evaluate the queryset for slicing
    submissions_list = list(filtered_submissions.order_by('-submission_date')[:50])
    
    for submission in submissions_list:
        data['submissions'].append({
            'form_type': submission.dynamic_form.form_type,
            'form_name': submission.dynamic_form.name,
            'faculty': submission.faculty.username,
            'status': submission.status,
            'submission_date': submission.submission_date.isoformat() if submission.submission_date else None,
            'course': submission.course.code if course_id is None else None
        })
    
    return data
