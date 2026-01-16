import re
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import Course, User, Department, DynamicForm, FormQuestion, DynamicFormSubmission, FormAnswer, CourseFaculty, CourseOutline, AnalyticsCache
from django.db.models import Count, Q, F
from datetime import datetime, timedelta
import difflib
from django.utils.html import escape
from django.utils.html import strip_tags

def is_admin(user):
    return user.is_authenticated and user.role == User.ROLE_ADMIN

def is_admin_or_crc(user):
    return user.is_authenticated and user.role in [User.ROLE_ADMIN, User.ROLE_CRC_MEMBER]

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

# Department Detail
@login_required
@user_passes_test(is_admin)
@require_http_methods(["GET"])
def api_department_detail(request, department_id):
    try:
        department = Department.objects.get(id=department_id)
        
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
    except Department.DoesNotExist:
        return JsonResponse({'error': 'Department not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

# Course API Views
@login_required
@user_passes_test(is_admin)
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
@login_required
@user_passes_test(is_admin)
@csrf_exempt
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
# Check form availability for faculty (UNIVERSAL FORMS ONLY)

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
        if existing_submission and existing_submission.status == 'submitted' and status == 'submitted':
            return JsonResponse({'error': 'You have already submitted this form for the selected course'}, status=400)
        
        # Create or update submission
        if existing_submission:
            submission = existing_submission
            submission.status = status
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
                status=status
            )
        
        # Create answers
        for question_id, answer_value in answers.items():
            try:
                question = FormQuestion.objects.get(id=question_id, form=form)
                
                # Handle different answer types
                if isinstance(answer_value, list) or isinstance(answer_value, dict):
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
                continue
        
        return JsonResponse({
            'message': 'Form saved successfully', 
            'submission_id': submission.id,
            'status': submission.status
        })
        
    except Course.DoesNotExist:
        return JsonResponse({'error': 'Course not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# Faculty Users API
@login_required
@user_passes_test(is_admin)
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
@user_passes_test(is_admin)
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
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_crc_analytics(request):
    """Generate analytics for form submissions"""
    try:
        form_id = request.GET.get('form_id')
        course_id = request.GET.get('course_id')
        question_id = request.GET.get('question_id')
        
        # Get analytics from cache or generate new
        cache_key = f"analytics_{form_id}_{course_id}_{question_id}"
        
        # Try to get from cache
        cached = AnalyticsCache.objects.filter(
            form_id=form_id if form_id else None,
            course_id=course_id if course_id else None,
            analytics_type='summary'
        ).first()
        
        if cached:
            return JsonResponse(cached.data)
        
        # Generate new analytics
        submissions = DynamicFormSubmission.objects.all()
        
        if form_id:
            submissions = submissions.filter(dynamic_form_id=form_id)
        if course_id:
            submissions = submissions.filter(course_id=course_id)
        
        # Basic statistics
        total_submissions = submissions.count()
        ccr_submissions = submissions.filter(dynamic_form__form_type='ccr').count()
        crr_submissions = submissions.filter(dynamic_form__form_type='crr').count()
        
        # Status distribution
        status_counts = submissions.values('status').annotate(count=Count('id'))
        
        # Faculty distribution
        faculty_counts = submissions.values('faculty__username').annotate(count=Count('id'))
        
        # Course distribution
        course_counts = submissions.values('course__code', 'course__title').annotate(count=Count('id'))
        
        analytics_data = {
            'total_submissions': total_submissions,
            'ccr_submissions': ccr_submissions,
            'crr_submissions': crr_submissions,
            'status_distribution': list(status_counts),
            'faculty_distribution': list(faculty_counts),
            'course_distribution': list(course_counts),
            'generated_at': datetime.now().isoformat()
        }
        
        # If question_id is specified, get question-wise analytics
        if question_id:
            try:
                question = FormQuestion.objects.get(id=question_id)
                answers = FormAnswer.objects.filter(
                    question=question,
                    submission__in=submissions
                )
                
                if question.question_type in ['select', 'radio', 'checkbox']:
                    # For multiple choice questions
                    option_counts = {}
                    for answer in answers:
                        if answer.answer_data:
                            for option in answer.answer_data:
                                option_counts[option] = option_counts.get(option, 0) + 1
                        elif answer.answer_text:
                            option_counts[answer.answer_text] = option_counts.get(answer.answer_text, 0) + 1
                    
                    question_analytics = {
                        'question_text': question.question_text,
                        'question_type': question.question_type,
                        'total_responses': len(answers),
                        'option_counts': option_counts,
                        'most_frequent': max(option_counts, key=option_counts.get) if option_counts else None
                    }
                else:
                    # For text questions
                    text_responses = [answer.answer_text for answer in answers if answer.answer_text]
                    question_analytics = {
                        'question_text': question.question_text,
                        'question_type': question.question_type,
                        'total_responses': len(answers),
                        'text_responses_sample': text_responses[:10],
                        'total_text_responses': len(text_responses)
                    }
                
                analytics_data['question_analytics'] = question_analytics
                
            except FormQuestion.DoesNotExist:
                pass
        
        # Cache the analytics
        AnalyticsCache.objects.create(
            form_id=form_id if form_id else None,
            course_id=course_id if course_id else None,
            analytics_type='summary',
            data=analytics_data
        )
        
        return JsonResponse(analytics_data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_crc_export_analytics(request):
    """Export analytics as PDF (simplified - returns JSON for now)"""
    try:
        form_id = request.GET.get('form_id')
        
        # Get analytics data
        analytics_response = api_crc_analytics(request)
        analytics_data = json.loads(analytics_response.content)
        
        # In a real implementation, you would generate a PDF here
        # For now, return JSON with a message about PDF generation
        return JsonResponse({
            'message': 'PDF export functionality would be implemented here',
            'analytics_data': analytics_data,
            'export_format': 'pdf',
            'exported_at': datetime.now().isoformat()
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)



@login_required
@csrf_exempt
@require_http_methods(["POST"])
def api_save_course_outline(request):
    """Save or update course outline (faculty only) - WITH WORKFLOW RESTRICTIONS"""
    if request.user.role != User.ROLE_FACULTY:
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
        
        # Check if faculty is coordinator for this course
        try:
            course_assignment = CourseFaculty.objects.get(
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
    """Get course outline for faculty"""
    if request.user.role != User.ROLE_FACULTY:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        course_id = request.GET.get('course_id')
        
        # Check if faculty is coordinator for this course
        try:
            CourseFaculty.objects.get(
                faculty=request.user,
                course_id=course_id,
                is_coordinator=True
            )
        except CourseFaculty.DoesNotExist:
            return JsonResponse({'error': 'Only course coordinators can access course outlines'}, status=403)
        
        # Get latest outline for this course by this faculty
        outline = CourseOutline.objects.filter(
            course_id=course_id,
            faculty=request.user
        ).order_by('-version').first()
        
        if outline:
            outline_data = {
                'id': outline.id,
                'version': outline.version,
                'title': outline.title,
                'description': outline.description,
                'content': outline.content,
                'status': outline.status,
                'notes': outline.notes,
                'created_at': outline.created_at.isoformat() if outline.created_at else None,
                'submitted_at': outline.submitted_at.isoformat() if outline.submitted_at else None,
                'approved_at': outline.approved_at.isoformat() if outline.approved_at else None
            }
            return JsonResponse(outline_data)
        else:
            return JsonResponse({'exists': False})
            
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
    """Get all course outlines for the current faculty member"""
    if request.user.role != User.ROLE_FACULTY:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        outlines = CourseOutline.objects.filter(
            faculty=request.user
        ).select_related('course').order_by('-created_at')
        
        outlines_list = []
        for outline in outlines:
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
    """Get course outline structure for faculty (coordinators only) - NO TEMPLATE"""
    if request.user.role != User.ROLE_FACULTY:
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    try:
        course_id = request.GET.get('course_id')
        
        if not course_id:
            return JsonResponse({'error': 'course_id is required'}, status=400)
        
        # Check if faculty is coordinator for this course
        try:
            course_assignment = CourseFaculty.objects.get(
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

# Compare Outlines API
@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_crc_compare_outlines(request):
    """Compare old and new course outlines"""
    try:
        course_id = request.GET.get('course_id')
        new_outline_id = request.GET.get('new_outline_id')
        
        if not course_id or not new_outline_id:
            return JsonResponse({'error': 'course_id and new_outline_id are required'}, status=400)
        
        # Get new outline
        new_outline = CourseOutline.objects.get(id=new_outline_id)
        
        # Get current/old outline for comparison
        old_outline = CourseOutline.objects.filter(
            course_id=course_id,
            is_current=True,
            status='approved'
        ).exclude(id=new_outline_id).order_by('-version').first()
        
        comparison_data = {
            'course': {
                'id': new_outline.course.id,
                'code': new_outline.course.code,
                'title': new_outline.course.title
            },
            'new_outline': {
                'id': new_outline.id,
                'version': new_outline.version,
                'title': new_outline.title,
                'faculty': new_outline.faculty.username,
                'submitted_at': new_outline.submitted_at.isoformat() if new_outline.submitted_at else None
            },
            'old_outline': None,
            'comparison': {
                'major_changes': [],
                'minor_changes': [],
                'summary': 'No previous outline found for comparison'
            }
        }
        
        if old_outline:
            comparison_data['old_outline'] = {
                'id': old_outline.id,
                'version': old_outline.version,
                'title': old_outline.title,
                'approved_at': old_outline.approved_at.isoformat() if old_outline.approved_at else None
            }
            
            # Simple comparison
            old_content = old_outline.content or {}
            new_content = new_outline.content or {}
            
            major_changes = []
            minor_changes = []
            
            # Compare course info
            old_info = old_content.get('course_info', {})
            new_info = new_content.get('course_info', {})
            
            for key in ['course_name', 'course_code', 'credits']:
                if old_info.get(key) != new_info.get(key):
                    major_changes.append(f"Course {key.replace('_', ' ').title()} changed: '{old_info.get(key)}' → '{new_info.get(key)}'")
            
            # Compare sections
            old_sections = old_content.get('sections', [])
            new_sections = new_content.get('sections', [])
            
            for i, new_section in enumerate(new_sections):
                if i < len(old_sections):
                    old_section = old_sections[i]
                    if new_section.get('content') != old_section.get('content'):
                        if new_section.get('id') in ['calendar_activities', 'assessment', 'learning_outcomes']:
                            major_changes.append(f"Changes in {new_section.get('title', 'Section')}")
                        else:
                            minor_changes.append(f"Updates in {new_section.get('title', 'Section')}")
                else:
                    # New section added
                    major_changes.append(f"New section added: {new_section.get('title', 'Untitled')}")
            
            comparison_data['comparison'] = {
                'major_changes': major_changes,
                'minor_changes': minor_changes,
                'summary': f"Found {len(major_changes)} major and {len(minor_changes)} minor changes"
            }
        
        return JsonResponse(comparison_data)
        
    except CourseOutline.DoesNotExist:
        return JsonResponse({'error': 'Course outline not found'}, status=404)
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
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["POST"])
def api_compare_outlines_git_style(request):
    """GitHub-style diff comparison between two outlines - HIDES HTML TAGS"""
    try:
        data = json.loads(request.body)
        outline1_id = data.get('outline1_id')
        outline2_id = data.get('outline2_id')
        
        # Get outlines
        outline1 = CourseOutline.objects.get(id=outline1_id)
        outline2 = CourseOutline.objects.get(id=outline2_id)
        
        # Function to remove HTML tags and clean text
        def clean_html(text):
            """Remove HTML tags and clean text"""
            if not text:
                return ""
            
            # First, strip HTML tags
            text = strip_tags(str(text))
            
            # Remove multiple spaces
            text = re.sub(r'\s+', ' ', text)
            
            # Remove common HTML entities
            html_entities = {
                '&nbsp;': ' ',
                '&amp;': '&',
                '&lt;': '<',
                '&gt;': '>',
                '&quot;': '"',
                '&#39;': "'",
                '&ldquo;': '"',
                '&rdquo;': '"',
                '&lsquo;': "'",
                '&rsquo;': "'"
            }
            
            for entity, replacement in html_entities.items():
                text = text.replace(entity, replacement)
            
            return text.strip()
        
        # Convert content to clean text for comparison
        def content_to_clean_text(content):
            """Convert content to clean plain text for comparison"""
            if not content:
                return ""
            
            # If content is JSON string, try to parse it
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except:
                    # Clean HTML from string
                    return clean_html(content)
            
            # If it's a dict, extract all text
            if isinstance(content, dict):
                text_lines = []
                
                # Add course info
                if 'course_info' in content:
                    text_lines.append("=== COURSE INFORMATION ===")
                    for key, value in content['course_info'].items():
                        if value:
                            clean_value = clean_html(str(value))
                            if clean_value:
                                text_lines.append(f"{key.replace('_', ' ').title()}: {clean_value}")
                    text_lines.append("")
                
                # Add sections
                if 'sections' in content:
                    for section in content['sections']:
                        section_title = section.get('title', 'Untitled')
                        section_type = section.get('type', '')
                        
                        # Clean section title
                        clean_title = clean_html(section_title)
                        if clean_title:
                            text_lines.append(f"### {clean_title} ###")
                        
                        # Add content if present
                        if section.get('content'):
                            clean_content = clean_html(section['content'])
                            if clean_content:
                                # Split into lines if it's long
                                lines = clean_content.split('\n')
                                for line in lines:
                                    if line.strip():
                                        text_lines.append(line.strip())
                        
                        # Add rows for tables
                        if section.get('rows'):
                            for row in section['rows']:
                                if isinstance(row, dict):
                                    row_values = []
                                    for v in row.values():
                                        if v:
                                            clean_v = clean_html(str(v))
                                            if clean_v:
                                                row_values.append(clean_v)
                                    if row_values:
                                        text_lines.append(f"  {' | '.join(row_values)}")
                                elif isinstance(row, (list, tuple)):
                                    row_values = []
                                    for v in row:
                                        if v:
                                            clean_v = clean_html(str(v))
                                            if clean_v:
                                                row_values.append(clean_v)
                                    if row_values:
                                        text_lines.append(f"  {' | '.join(row_values)}")
                                elif row:
                                    clean_row = clean_html(str(row))
                                    if clean_row:
                                        text_lines.append(f"  {clean_row}")
                        
                        text_lines.append("")
                
                return "\n".join([line for line in text_lines if line.strip()])
            else:
                # Return cleaned plain string
                return clean_html(str(content))
        
        # Get clean text for comparison
        text1 = content_to_clean_text(outline1.content)
        text2 = content_to_clean_text(outline2.content)
        
        # Split into lines
        lines1 = text1.splitlines()
        lines2 = text2.splitlines()
        
        # Filter out empty lines (keep only lines with content)
        lines1 = [line for line in lines1 if line.strip()]
        lines2 = [line for line in lines2 if line.strip()]
        
        # Generate diff using Python's difflib
        diff = list(difflib.unified_diff(
            lines1, 
            lines2,
            fromfile=f"{outline1.course.code} v{outline1.version}",
            tofile=f"{outline2.course.code} v{outline2.version}",
            lineterm=""
        ))
        
        # Get detailed diff for side-by-side view
        differ = difflib.Differ()
        line_by_line_diff = list(differ.compare(lines1, lines2))
        
        # Process line-by-line diff
        line_changes = []
        line_number1 = 1
        line_number2 = 1
        
        for line in line_by_line_diff:
            line_type = line[0]
            line_content = line[2:]
            
            # Skip empty lines in diff
            if not line_content.strip() and line_type == ' ':
                continue
                
            if line_type == ' ':  # Unchanged
                line_changes.append({
                    'type': 'unchanged',
                    'old_line': line_content,
                    'new_line': line_content,
                    'old_line_num': line_number1,
                    'new_line_num': line_number2
                })
                line_number1 += 1
                line_number2 += 1
            elif line_type == '-':  # Removed
                line_changes.append({
                    'type': 'removed',
                    'old_line': line_content,
                    'new_line': '',
                    'old_line_num': line_number1,
                    'new_line_num': None
                })
                line_number1 += 1
            elif line_type == '+':  # Added
                line_changes.append({
                    'type': 'added',
                    'old_line': '',
                    'new_line': line_content,
                    'old_line_num': None,
                    'new_line_num': line_number2
                })
                line_number2 += 1
            elif line_type == '?':  # Change details (skip)
                continue
        
        # Calculate statistics
        total_lines_old = len(lines1)
        total_lines_new = len(lines2)
        
        # Calculate similarity
        matcher = difflib.SequenceMatcher(None, text1, text2)
        similarity = matcher.ratio() * 100
        
        # Get section changes
        section_changes = {}
        current_section = "General"
        
        for change in line_changes:
            line = change.get('old_line') or change.get('new_line') or ''
            
            # Check if this is a section header
            if line.startswith('###'):
                current_section = line.replace('###', '').strip()
                if current_section not in section_changes:
                    section_changes[current_section] = {'added': 0, 'removed': 0}
            elif change['type'] in ['added', 'removed']:
                if current_section not in section_changes:
                    section_changes[current_section] = {'added': 0, 'removed': 0}
                
                if change['type'] == 'added':
                    section_changes[current_section]['added'] += 1
                else:
                    section_changes[current_section]['removed'] += 1
        
        # Count added/removed lines
        added_lines = sum(1 for c in line_changes if c['type'] == 'added')
        removed_lines = sum(1 for c in line_changes if c['type'] == 'removed')
        
        return JsonResponse({
            'success': True,
            'diff': diff,
            'line_changes': line_changes,
            'statistics': {
                'similarity': round(similarity, 1),
                'total_lines_old': total_lines_old,
                'total_lines_new': total_lines_new,
                'added_lines': added_lines,
                'removed_lines': removed_lines,
                'total_changes': added_lines + removed_lines,
                'change_percentage': round(((added_lines + removed_lines) / max(total_lines_old, total_lines_new)) * 100, 1) if max(total_lines_old, total_lines_new) > 0 else 0
            },
            'outline1': {
                'id': outline1.id,
                'code': outline1.course.code,
                'title': outline1.title,
                'faculty': outline1.faculty.username,
                'status': outline1.status,
                'version': outline1.version,
                'text': text1
            },
            'outline2': {
                'id': outline2.id,
                'code': outline2.course.code,
                'title': outline2.title,
                'faculty': outline2.faculty.username,
                'status': outline2.status,
                'version': outline2.version,
                'text': text2
            },
            'section_changes': section_changes
        })
        
    except Exception as e:
        import traceback
        print(f"Error in diff comparison: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({
            'success': False,
            'error': str(e)
        })