import re
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import Course, User, Department, DynamicForm, FormQuestion, DynamicFormSubmission, FormAnswer, CourseFaculty, CourseOutline
from django.db.models import Count, Q, F
from datetime import datetime, timedelta


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


# Analysis APIs
@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_analysis_form_submissions_over_time(request):
    """Get form submissions over time (last 8 weeks) for line chart"""
    try:
        import datetime
        from django.db.models.functions import TruncWeek
        from django.db.models import Count
        
        # Get submissions from last 8 weeks
        eight_weeks_ago = datetime.datetime.now() - datetime.timedelta(weeks=8)
        
        # Get submissions grouped by week
        submissions_by_week = DynamicFormSubmission.objects.filter(
            submission_date__gte=eight_weeks_ago,
            dynamic_form__form_type__in=['ccr', 'crr']
        ).annotate(
            week=TruncWeek('submission_date')
        ).values('week', 'dynamic_form__form_type').annotate(
            count=Count('id')
        ).order_by('week')
        
        # Format data for chart
        weeks = []
        ccr_data = []
        crr_data = []
        
        # Initialize with zeros for last 8 weeks
        for i in range(8):
            week_start = (datetime.datetime.now() - datetime.timedelta(weeks=i)).date()
            week_start = week_start - datetime.timedelta(days=week_start.weekday())
            weeks.insert(0, week_start.strftime('%Y-%m-%d'))
            ccr_data.insert(0, 0)
            crr_data.insert(0, 0)
        
        # Fill in actual data
        for entry in submissions_by_week:
            week_str = entry['week'].strftime('%Y-%m-%d')
            if week_str in weeks:
                idx = weeks.index(week_str)
                if entry['dynamic_form__form_type'] == 'ccr':
                    ccr_data[idx] = entry['count']
                else:
                    crr_data[idx] = entry['count']
        
        return JsonResponse({
            'weeks': weeks,
            'ccr_submissions': ccr_data,
            'crr_submissions': crr_data,
            'total_submissions': sum(ccr_data) + sum(crr_data)
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_analysis_form_status_distribution(request):
    """Get form status distribution for pie chart"""
    try:
        # Get status counts for CCR and CRR forms separately
        ccr_status = DynamicFormSubmission.objects.filter(
            dynamic_form__form_type='ccr'
        ).values('status').annotate(
            count=Count('id')
        ).order_by('status')
        
        crr_status = DynamicFormSubmission.objects.filter(
            dynamic_form__form_type='crr'
        ).values('status').annotate(
            count=Count('id')
        ).order_by('status')
        
        # Format data
        status_labels = ['Submitted', 'Approved', 'Revision Requested', 'Draft']
        ccr_counts = {item['status']: item['count'] for item in ccr_status}
        crr_counts = {item['status']: item['count'] for item in crr_status}
        
        ccr_data = []
        crr_data = []
        
        for status in ['submitted', 'approved', 'revision_requested', 'draft']:
            ccr_data.append(ccr_counts.get(status, 0))
            crr_data.append(crr_counts.get(status, 0))
        
        return JsonResponse({
            'labels': status_labels,
            'ccr_data': ccr_data,
            'crr_data': crr_data,
            'total_ccr': sum(ccr_data),
            'total_crr': sum(crr_data)
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_analysis_clo_achievement(request):
    """Get CLO achievement rate analysis from form answers"""
    try:
        # This would analyze form answers to calculate CLO achievement rates
        # For now, we'll use mock data based on form submissions
        
        # Get all form submissions with answers
        submissions = DynamicFormSubmission.objects.filter(
            dynamic_form__form_type__in=['ccr', 'crr']
        ).select_related('dynamic_form').prefetch_related('answers')
        
        clo_achievement = {
            'clo1': {'achieved': 0, 'total': 0, 'rate': 0},
            'clo2': {'achieved': 0, 'total': 0, 'rate': 0},
            'clo3': {'achieved': 0, 'total': 0, 'rate': 0},
            'clo4': {'achieved': 0, 'total': 0, 'rate': 0}
        }
        
        # Analyze answers for CLO-related questions
        for submission in submissions:
            answers = submission.answers.filter(
                question__question_text__icontains='CLO'
            )
            
            for answer in answers:
                # Extract CLO number from question text
                import re
                clo_match = re.search(r'CLO\s*(\d+)', answer.question.question_text, re.IGNORECASE)
                if clo_match:
                    clo_num = clo_match.group(1)
                    clo_key = f'clo{clo_num}'
                    
                    if clo_key in clo_achievement:
                        clo_achievement[clo_key]['total'] += 1
                        
                        # Check if answer indicates achievement
                        answer_text = answer.answer_text.lower() if answer.answer_text else ''
                        answer_data = str(answer.answer_data).lower() if answer.answer_data else ''
                        
                        # Simple heuristics for achievement
                        achievement_keywords = ['yes', 'achieved', 'completed', 'satisfactory', 'good', 'excellent', 'pass']
                        if any(keyword in answer_text for keyword in achievement_keywords) or \
                           any(keyword in answer_data for keyword in achievement_keywords):
                            clo_achievement[clo_key]['achieved'] += 1
        
        # Calculate rates
        for clo in clo_achievement.values():
            if clo['total'] > 0:
                clo['rate'] = round((clo['achieved'] / clo['total']) * 100, 1)
        
        return JsonResponse({
            'clo_labels': ['CLO 1', 'CLO 2', 'CLO 3', 'CLO 4'],
            'achievement_rates': [
                clo_achievement['clo1']['rate'],
                clo_achievement['clo2']['rate'],
                clo_achievement['clo3']['rate'],
                clo_achievement['clo4']['rate']
            ],
            'total_assessments': sum(clo['total'] for clo in clo_achievement.values()),
            'average_rate': round(
                sum(clo['rate'] for clo in clo_achievement.values()) / 4, 1
            ) if any(clo['total'] > 0 for clo in clo_achievement.values()) else 0
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

# Outline Comparison APIs
@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_analysis_courses_with_outlines(request):
    """Get all courses that have outlines"""
    try:
        courses_with_outlines = Course.objects.filter(
            outlines__isnull=False
        ).distinct().values('id', 'code', 'title', 'department__name')
        
        return JsonResponse(list(courses_with_outlines), safe=False)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin_or_crc)
@require_http_methods(["GET"])
def api_analysis_course_outline_versions(request, course_id):
    """Get all outline versions for a course"""
    try:
        outlines = CourseOutline.objects.filter(
            course_id=course_id
        ).values('id', 'version', 'title', 'status', 'created_at', 'faculty__username')
        
        return JsonResponse(list(outlines), safe=False)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["POST"])
def api_analysis_compare_outlines(request):
    """Compare two outline versions"""
    try:
        import difflib
        from html import escape
        
        data = json.loads(request.body)
        outline1_id = data.get('outline1_id')
        outline2_id = data.get('outline2_id')
        
        if not outline1_id or not outline2_id:
            return JsonResponse({'error': 'Both outline IDs are required'}, status=400)
        
        outline1 = CourseOutline.objects.get(id=outline1_id)
        outline2 = CourseOutline.objects.get(id=outline2_id)
        
        # Get content for comparison
        content1 = outline1.content or ""
        content2 = outline2.content or ""
        
        # Simple text comparison using difflib
        d = difflib.Differ()
        diff = list(d.compare(
            content1.splitlines(keepends=True),
            content2.splitlines(keepends=True)
        ))
        
        # Categorize changes
        added = []
        deleted = []
        modified = []
        
        for line in diff:
            if line.startswith('+ ') and not line.startswith('+  '):
                added.append(escape(line[2:]))
            elif line.startswith('- ') and not line.startswith('-  '):
                deleted.append(escape(line[2:]))
            elif line.startswith('? '):
                modified.append(escape(line[2:]))
        
        # Calculate similarity percentage
        similarity = difflib.SequenceMatcher(
            None, 
            content1, 
            content2
        ).ratio() * 100
        
        return JsonResponse({
            'outline1': {
                'id': outline1.id,
                'version': outline1.version,
                'title': outline1.title,
                'faculty': outline1.faculty.username,
                'created_at': outline1.created_at.strftime('%Y-%m-%d')
            },
            'outline2': {
                'id': outline2.id,
                'version': outline2.version,
                'title': outline2.title,
                'faculty': outline2.faculty.username,
                'created_at': outline2.created_at.strftime('%Y-%m-%d')
            },
            'comparison': {
                'similarity_percentage': round(similarity, 2),
                'lines_added': len(added),
                'lines_deleted': len(deleted),
                'lines_modified': len(modified),
                'added_lines': added,
                'deleted_lines': deleted,
                'modified_lines': modified
            }
        })
        
    except CourseOutline.DoesNotExist:
        return JsonResponse({'error': 'One or both outlines not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

# CQI Report APIs (NLP-based)
@login_required
@user_passes_test(is_admin_or_crc)
@csrf_exempt
@require_http_methods(["POST"])
def api_analysis_generate_cqi_report(request):
    """Generate CQI report using NLP analysis"""
    try:
        import re
        from collections import Counter
        from datetime import datetime, timedelta
        
        data = json.loads(request.body)
        report_type = data.get('report_type', 'comprehensive')  # 'comprehensive', 'forms', 'outlines'
        time_period = data.get('time_period', 'last_month')  # 'last_month', 'last_quarter', 'all_time'
        
        # Calculate date range
        end_date = datetime.now()
        if time_period == 'last_month':
            start_date = end_date - timedelta(days=30)
        elif time_period == 'last_quarter':
            start_date = end_date - timedelta(days=90)
        else:
            start_date = datetime.min
        
        # Get data for analysis
        form_submissions = DynamicFormSubmission.objects.filter(
            submission_date__range=(start_date, end_date),
            dynamic_form__form_type__in=['ccr', 'crr']
        ).select_related('faculty', 'course', 'dynamic_form').prefetch_related('answers')
        
        course_outlines = CourseOutline.objects.filter(
            submitted_at__range=(start_date, end_date)
        ).select_related('faculty', 'course')
        
        # Extract text data for NLP analysis
        all_text_data = []
        
        # Collect form answers
        for submission in form_submissions:
            for answer in submission.answers.all():
                if answer.answer_text:
                    all_text_data.append(answer.answer_text)
        
        # Collect outline content
        for outline in course_outlines:
            if outline.content:
                all_text_data.append(outline.content)
        
        # Simple NLP analysis (you can replace this with more sophisticated NLP)
        common_issues = []
        suggestions = []
        strengths = []
        
        # Analyze text for common patterns
        text_combined = ' '.join(all_text_data).lower()
        
        # Look for common issues
        issue_patterns = {
            'Time Management': ['not enough time', 'time constraint', 'rushed', 'schedule issue'],
            'Resources': ['lack of resources', 'no textbook', 'limited access', 'equipment issue'],
            'Assessment': ['difficult exam', 'unclear grading', 'assessment issue', 'rubric problem'],
            'Content Coverage': ['too much content', 'syllabus overload', 'coverage issue'],
            'Student Engagement': ['low participation', 'student disengagement', 'attendance issue'],
        }
        
        for issue, keywords in issue_patterns.items():
            count = sum(text_combined.count(keyword) for keyword in keywords)
            if count > 0:
                common_issues.append({
                    'issue': issue,
                    'frequency': count,
                    'examples': [kw for kw in keywords if kw in text_combined][:3]
                })
        
        # Look for strengths
        strength_patterns = {
            'Good Resources': ['excellent resources', 'good materials', 'helpful content', 'useful tools'],
            'Effective Assessment': ['fair assessment', 'clear rubric', 'helpful feedback', 'good evaluation'],
            'Student Engagement': ['active participation', 'good discussion', 'engaged students', 'high attendance'],
            'Content Quality': ['excellent content', 'well organized', 'clear structure', 'comprehensive'],
        }
        
        for strength, keywords in strength_patterns.items():
            count = sum(text_combined.count(keyword) for keyword in keywords)
            if count > 0:
                strengths.append({
                    'strength': strength,
                    'frequency': count,
                    'examples': [kw for kw in keywords if kw in text_combined][:3]
                })
        
        # Generate suggestions based on analysis
        if common_issues:
            suggestions = [
                "Consider allocating more time for complex topics based on faculty feedback.",
                "Review resource availability and consider additional learning materials.",
                "Provide clearer assessment rubrics and expectations to students.",
                "Consider revising content coverage to better match available time."
            ]
        
        # Generate summary statistics
        stats = {
            'total_form_submissions': form_submissions.count(),
            'total_course_outlines': course_outlines.count(),
            'time_period': time_period,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'top_faculty_contributors': list(
                form_submissions.values('faculty__username')
                .annotate(count=Count('id'))
                .order_by('-count')[:5]
                .values('faculty__username', 'count')
            ),
            'most_active_courses': list(
                form_submissions.values('course__code', 'course__title')
                .annotate(count=Count('id'))
                .order_by('-count')[:5]
                .values('course__code', 'course__title', 'count')
            )
        }
        
        return JsonResponse({
            'report_type': report_type,
            'generated_at': datetime.now().isoformat(),
            'statistics': stats,
            'common_issues': common_issues[:5],  # Top 5 issues
            'key_strengths': strengths[:5],  # Top 5 strengths
            'recommendations': suggestions,
            'analysis_summary': f"Analysis of {len(all_text_data)} text entries from {stats['total_form_submissions']} form submissions and {stats['total_course_outlines']} course outlines."
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)