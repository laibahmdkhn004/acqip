from django.urls import path
from . import views
from . import api_views

urlpatterns = [
    # root route
    path("", views.landing_page, name="home"),  # Landing page as home
    path("dashboard/", views.dashboard, name="dashboard"),  # Your existing dashboard
    
    # authentication
    path("register/", views.register, name="register"),
    path("login/", views.CustomLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),  

    # dashboard (role-based)
    path("dashboard/", views.dashboard, name="dashboard"),
    path("faculty-dashboard/", views.faculty_dashboard, name="faculty_dashboard"),
    path("crc-dashboard/", views.crc_dashboard, name="crc_dashboard"),
    
    # Course Outline Editor
    path("course-outline-editor/", views.course_outline_editor, name="course_outline_editor"),
    path("course-outline/", views.course_outline_view, name="course_outline"),
    
    # Dynamic Form URLs
    path("dynamic-form/", views.dynamic_form, name="dynamic_form"),
    path("submissions/", views.ccr_submissions, name="ccr_submissions"),

    # API endpoints for admin dashboard
    path("api/departments/", api_views.api_departments, name="api_departments"),
    path("api/departments/create/", api_views.api_departments_create, name="api_departments_create"),
    path("api/departments/<int:department_id>/", api_views.api_department_detail, name="api_department_detail"),
    
    path("api/courses/", api_views.api_courses, name="api_courses"),
    path("api/courses/create/", api_views.api_courses_create, name="api_courses_create"),
    path("api/courses/<int:course_id>/", api_views.api_course_update, name="api_course_update"),
    path("api/courses/<int:course_id>/delete/", api_views.api_course_delete, name="api_course_delete"),
    path("api/courses/<int:course_id>/assign-faculty/", api_views.api_assign_course_faculty, name="api_assign_course_faculty"),
    
    path("api/forms/", api_views.api_forms, name="api_forms"),
    path("api/forms/create/", api_views.api_dynamic_forms_create, name="api_dynamic_forms_create"),
    path("api/forms/<int:form_id>/", api_views.api_form_update, name="api_form_update"),
    path("api/forms/<int:form_id>/delete/", api_views.api_form_delete, name="api_form_delete"),
    
    path("api/users/", api_views.api_users, name="api_users"),
    path("api/users/create/", api_views.api_users_create, name="api_users_create"),
    path("api/users/<int:user_id>/", api_views.api_user_update, name="api_user_update"),
    path("api/users/<int:user_id>/delete/", api_views.api_user_delete, name="api_user_delete"),
    
    # Faculty assignment APIs
    path("api/faculty/<int:user_id>/assign-courses/", api_views.api_assign_courses_to_faculty, name="api_assign_courses_to_faculty"),
    path("api/faculty/my-courses/", api_views.api_faculty_courses, name="api_faculty_courses"),
    
    # Dynamic Form API URLs
    path("api/dynamic-forms/", api_views.api_dynamic_forms, name="api_dynamic_forms"),
    path("api/dynamic-forms/create/", api_views.api_dynamic_forms_create, name="api_dynamic_forms_create"),
    path("api/dynamic-forms/<int:form_id>/", api_views.api_dynamic_form_update, name="api_dynamic_form_update"),
    path("api/dynamic-forms/<int:form_id>/delete/", api_views.api_dynamic_form_delete, name="api_dynamic_form_delete"),
    
    # Form Questions API
    path("api/dynamic-forms/<int:form_id>/questions/", api_views.api_form_questions, name="api_form_questions"),
    path("api/dynamic-forms/<int:form_id>/questions/create/", api_views.api_form_questions_create, name="api_form_questions_create"),
    path("api/questions/<int:question_id>/", api_views.api_form_question_update, name="api_form_question_update"),
    path("api/questions/<int:question_id>/delete/", api_views.api_form_question_delete, name="api_form_question_delete"),
    
    # Dynamic Form Submissions
    path("api/dynamic-submissions/", api_views.api_dynamic_submissions, name="api_dynamic_submissions"),
    
    # Faculty Dynamic Forms
    path("api/faculty/dynamic-forms/", api_views.api_faculty_dynamic_forms, name="api_faculty_dynamic_forms"),
    path("api/dynamic-form/submit/", api_views.api_submit_dynamic_form, name="api_submit_dynamic_form"),
    
    # Faculty Users API
    path("api/faculty-users/", api_views.api_faculty_users, name="api_faculty_users"),
    path("api/courses/<int:course_id>/faculty-assignments/", api_views.api_course_faculty_assignments, name="api_course_faculty_assignments"),
    
    # Submission Details
    path("api/submission-details/<int:submission_id>/", api_views.api_submission_details, name="api_submission_details"),
    
    # Faculty-specific APIs
    path("api/faculty/submissions/", api_views.api_faculty_submissions_list, name="api_faculty_submissions_list"),
    path("api/faculty/course-outlines/", api_views.api_faculty_course_outlines, name="api_faculty_course_outlines"),
    path("api/faculty/profile/update/", api_views.api_faculty_profile_update, name="api_faculty_profile_update"),
    
    # Course Outline APIs
    path("api/save-course-outline/", api_views.api_save_course_outline, name="api_save_course_outline"),
    path("api/get-course-outline/", api_views.api_get_course_outline, name="api_get_course_outline"),
    path("api/faculty/course-outline-structure/", api_views.api_faculty_course_outline_structure, name="api_faculty_course_outline_structure"),
    
    # CRC Specific APIs
    path("api/crc/faculty-list/", api_views.api_crc_faculty_list, name="api_crc_faculty_list"),
    path("api/crc/course-catalogue/", api_views.api_crc_course_catalogue, name="api_crc_course_catalogue"),
    path("api/crc/update-course-outline/", api_views.api_crc_update_course_outline, name="api_crc_update_course_outline"),
    path("api/crc/course-outline-submissions/", api_views.api_crc_course_outline_submissions, name="api_crc_course_outline_submissions"),
    path("api/crc/form-submissions/", api_views.api_crc_form_submissions, name="api_crc_form_submissions"),
   
    # Form Publishing APIs
    path("api/publish-form/<int:form_id>/", api_views.api_publish_form, name="api_publish_form"),
    path("api/unpublish-form/<int:form_id>/", api_views.api_unpublish_form, name="api_unpublish_form"),
    
    # Submission Approval APIs
    path("api/submissions/<int:submission_id>/approve/", api_views.api_approve_submission, name="api_approve_submission"),
    path("api/submissions/<int:submission_id>/reject/", api_views.api_reject_submission, name="api_reject_submission"),
    path("api/submissions/<int:submission_id>/request-revision/", api_views.api_request_revision_submission, name="api_request_revision_submission"),
    
    # Admin Password Reset
    path("api/admin/reset-faculty-password/<int:user_id>/", api_views.api_admin_reset_faculty_password, name="api_admin_reset_faculty_password"),
    
    # CRC Dashboard Stats
    path("api/crc/dashboard-stats/", api_views.api_crc_dashboard_stats, name="api_crc_dashboard_stats"),

    # New endpoints for form availability
    path("api/faculty/form-availability/", api_views.api_faculty_form_availability, name="api_faculty_form_availability"),
    path("api/crc/outline-content/<int:outline_id>/", api_views.api_crc_view_outline_content, name="api_crc_view_outline_content"),
    
    # Check outline permissions
    path("api/outline-permissions/<int:outline_id>/", api_views.api_check_outline_permissions, name="api_check_outline_permissions"),
    
    # Form availability endpoint
    path("api/form-availability/", api_views.api_form_availability, name="api_form_availability"),
    
    # Department update endpoint
    path("api/departments/<int:department_id>/update/", api_views.api_department_update, name="api_department_update"),

# Add these to your urlpatterns in urls.py:

    # New Analysis and Reporting URLs
    path("api/crc/analysis/submissions-over-time/", api_views.api_analysis_submissions_over_time, name="api_analysis_submissions_over_time"),
    path("api/crc/analysis/form-status/", api_views.api_analysis_form_status, name="api_analysis_form_status"),
    path("api/crc/analysis/clo-achievement/", api_views.api_analysis_clo_achievement, name="api_analysis_clo_achievement"),
    path("api/crc/compare-outlines/", api_views.api_compare_outlines, name="api_compare_outlines"),
    path("api/crc/generate-cqi-report/", api_views.api_generate_cqi_report, name="api_generate_cqi_report"),
# Add these new URLs
path("api/crc/analysis/detailed-clo/<int:clo_number>/", api_views.api_analysis_detailed_clo, name="api_analysis_detailed_clo"),
path("api/crc/analysis/clo-trends/", api_views.api_analysis_clo_trends, name="api_analysis_clo_trends"),

path("api/crc/analysis/clo-by-course/", api_views.api_analysis_clo_by_course, name="api_analysis_clo_by_course"),



]