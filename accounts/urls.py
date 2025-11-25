from django.urls import path
from . import views
from . import api_views

urlpatterns = [
    # root route
    path("", views.home, name="home"),

    # authentication
    path("register/", views.register, name="register"),
    path("login/", views.CustomLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),  

    # dashboard (role-based)
    path("dashboard/", views.dashboard, name="dashboard"),

    # CCR Form URLs
    path("ccr/", views.ccr_form, name="ccr_form"),
    path("ccr/submissions/", views.ccr_submissions, name="ccr_submissions"),

    # API endpoints for admin dashboard
    path("api/departments/", api_views.api_departments, name="api_departments"),
    path("api/departments/create/", api_views.api_departments_create, name="api_departments_create"),
    path("api/departments/<int:department_id>/", api_views.api_department_detail, name="api_department_detail"),
    
    path("api/courses/", api_views.api_courses, name="api_courses"),
    path("api/courses/create/", api_views.api_courses_create, name="api_courses_create"),
    path("api/courses/<int:course_id>/", api_views.api_course_update, name="api_course_update"),
    path("api/courses/<int:course_id>/delete/", api_views.api_course_delete, name="api_course_delete"),
    
    path("api/forms/", api_views.api_forms, name="api_forms"),
    path("api/forms/create/", api_views.api_forms_create, name="api_forms_create"),
    path("api/forms/<int:form_id>/", api_views.api_form_update, name="api_form_update"),
    path("api/forms/<int:form_id>/delete/", api_views.api_form_delete, name="api_form_delete"),
    
    path("api/users/", api_views.api_users, name="api_users"),
    path("api/users/create/", api_views.api_users_create, name="api_users_create"),
    path("api/users/<int:user_id>/", api_views.api_user_update, name="api_user_update"),
    path("api/users/<int:user_id>/delete/", api_views.api_user_delete, name="api_user_delete"),
    
    # Faculty assignment APIs
    path("api/faculty/<int:user_id>/assign-courses/", api_views.api_assign_courses_to_faculty, name="api_assign_courses_to_faculty"),
    path("api/faculty/my-courses/", api_views.api_faculty_courses, name="api_faculty_courses"),
    
    # CCR API URLs
    path("api/ccr-forms/", api_views.api_ccr_forms, name="api_ccr_forms"),
    path("api/ccr-forms/toggle/", api_views.api_ccr_forms_toggle, name="api_ccr_forms_toggle"),
    path("api/ccr-submissions/", api_views.api_ccr_submissions, name="api_ccr_submissions"),
]
