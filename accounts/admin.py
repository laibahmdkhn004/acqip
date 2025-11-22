from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Course, Form, Department

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_superuser')
    fieldsets = UserAdmin.fieldsets + (
        ('Role', {'fields': ('role',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Role', {'fields': ('role',)}),
    )

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'created_at')
    search_fields = ('name', 'code')
    list_filter = ('created_at',)

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'code', 'department', 'created_at')
    search_fields = ('title', 'code', 'department__name')
    list_filter = ('department', 'created_at')
    filter_horizontal = ('faculty',)

@admin.register(Form)
class FormAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)
    list_filter = ('created_at',)