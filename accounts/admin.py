from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django import forms
from .models import User, Course, Form, Department, CCRForm, CCRSubmission, DynamicForm, FormQuestion, DynamicFormSubmission, FormAnswer

# Custom form for FormQuestion to ensure choices are updated
class FormQuestionForm(forms.ModelForm):
    class Meta:
        model = FormQuestion
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Force the choices to be from the current model
        self.fields['question_type'].choices = FormQuestion.QUESTION_TYPES

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

@admin.register(CCRForm)
class CCRFormAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'created_at')
    list_editable = ('status',)
    list_filter = ('status', 'created_at')
    
    def has_add_permission(self, request):
        if CCRForm.objects.filter(name="CCR Form").exists():
            return False
        return super().has_add_permission(request)

@admin.register(CCRSubmission)
class CCRSubmissionAdmin(admin.ModelAdmin):
    list_display = ('faculty', 'course', 'course_coordinator', 'submission_date')
    list_filter = ('submission_date', 'course')
    search_fields = ('faculty__username', 'course__title', 'course_coordinator')
    readonly_fields = ('submission_date', 'updated_at')

# Dynamic Form Admin
class FormQuestionInline(admin.TabularInline):
    model = FormQuestion
    form = FormQuestionForm
    extra = 1
    fields = ('question_text', 'question_type', 'order', 'required', 'options', 'help_text')
    ordering = ('order',)
@admin.register(DynamicForm)
class DynamicFormAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'created_at')
    list_editable = ('status',)
    list_filter = ('status', 'created_at')
    inlines = [FormQuestionInline]
    
    def has_add_permission(self, request):
        return True

@admin.register(FormQuestion)
class FormQuestionAdmin(admin.ModelAdmin):
    form = FormQuestionForm
    list_display = ('question_text', 'form', 'question_type', 'order', 'required')
    list_filter = ('form', 'question_type', 'required')
    search_fields = ('question_text',)
    ordering = ('form', 'order')
    fieldsets = (
        (None, {
            'fields': ('form', 'question_text', 'question_type', 'order', 'required', 'help_text')
        }),
        ('Options', {
            'fields': ('options',),
            'description': 'For checkbox, select, and radio types, provide options separated by commas',
        }),
    )
@admin.register(DynamicFormSubmission)
class DynamicFormSubmissionAdmin(admin.ModelAdmin):
    list_display = ('faculty', 'course', 'course_coordinator', 'submission_date')
    list_filter = ('submission_date', 'course', 'dynamic_form')
    search_fields = ('faculty__username', 'course__title', 'course_coordinator')
    readonly_fields = ('submission_date', 'updated_at')

@admin.register(FormAnswer)
class FormAnswerAdmin(admin.ModelAdmin):
    list_display = ('submission', 'question', 'answer_text')
    list_filter = ('question__form',)
    search_fields = ('answer_text', 'submission__faculty__username')
    readonly_fields = ('submission', 'question')