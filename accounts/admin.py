# admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django import forms
from .models import User, Course, Department, Section, DynamicForm, FormQuestion, DynamicFormSubmission, FormAnswer, CourseFaculty, CourseOutline, AnalyticsCache
from django.utils.html import format_html

# Custom form for FormQuestion
class FormQuestionForm(forms.ModelForm):
    class Meta:
        model = FormQuestion
        fields = '__all__'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['question_type'].choices = FormQuestion.QUESTION_TYPES

# Inline for CourseFaculty
class CourseFacultyInline(admin.TabularInline):
    model = CourseFaculty
    extra = 1
    raw_id_fields = ('faculty',)
    autocomplete_fields = ('sections',)

# Inline for Course Outline versions
class CourseOutlineInline(admin.TabularInline):
    model = CourseOutline
    extra = 0
    readonly_fields = ('version', 'status', 'created_at')
    can_delete = False

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role', 'department', 'designation', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_superuser', 'department', 'is_active')
    fieldsets = UserAdmin.fieldsets + (
        ('Role and Department', {'fields': ('role', 'department', 'designation')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Role and Department', {'fields': ('role', 'department', 'designation')}),
    )
    list_editable = ('is_active',)

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'created_at', 'course_count')
    search_fields = ('name', 'code')
    list_filter = ('created_at',)
    
    def course_count(self, obj):
        return obj.courses.count()
    course_count.short_description = 'Courses'


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'created_at')
    search_fields = ('name', 'code')
    list_filter = ('created_at',)

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'code', 'department', 'credits', 'catalogue_file', 'created_at', 'faculty_count')
    search_fields = ('title', 'code', 'department__name')
    list_filter = ('department', 'created_at')
    inlines = [CourseFacultyInline, CourseOutlineInline]
    
    def faculty_count(self, obj):
        return obj.faculty.count()
    faculty_count.short_description = 'Faculty'

@admin.register(CourseFaculty)
class CourseFacultyAdmin(admin.ModelAdmin):
    list_display = ('course', 'faculty', 'is_coordinator', 'section_list', 'created_at')
    list_filter = ('is_coordinator', 'created_at', 'course__department')
    search_fields = ('course__title', 'faculty__username', 'sections__code', 'sections__name')
    list_editable = ('is_coordinator',)
    filter_horizontal = ('sections',)

    def section_list(self, obj):
        return obj.section_display() or '—'
    section_list.short_description = 'Sections'

# Dynamic Form Admin
class FormQuestionInline(admin.TabularInline):
    model = FormQuestion
    form = FormQuestionForm
    extra = 1
    fields = ('question_text', 'question_type', 'order', 'required', 'options', 'help_text')
    ordering = ('order',)


# admin.py - Update DynamicFormAdmin
# admin.py - Update DynamicFormAdmin publish_form method
@admin.register(DynamicForm)
class DynamicFormAdmin(admin.ModelAdmin):
    list_display = ('name', 'form_type', 'status', 'question_count', 'created_at')
    list_editable = ('status',)
    list_filter = ('status', 'form_type', 'created_at')
    inlines = [FormQuestionInline]
    actions = ['publish_form', 'unpublish_form']
    
    def question_count(self, obj):
        return obj.questions.count()
    question_count.short_description = 'Questions'
    
    def publish_form(self, request, queryset):
        # REMOVED: Deactivating other forms of same type
        for form in queryset:
            # Allow both CCR and CRR forms to be active simultaneously
            if form.form_type in ['ccr', 'crr']:
                form.status = 'active'
                form.save()
        self.message_user(request, f"{queryset.count()} form(s) published.")
    publish_form.short_description = "Publish selected forms"
    
    def unpublish_form(self, request, queryset):
        queryset.update(status='inactive')
        self.message_user(request, f"{queryset.count()} form(s) unpublished.")
    unpublish_form.short_description = "Unpublish selected forms"

    
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
    list_display = ('faculty', 'course', 'assigned_section', 'section', 'dynamic_form', 'status', 'is_coordinator', 'submission_date', 'answer_count')
    list_filter = ('status', 'submission_date', 'course', 'dynamic_form', 'is_coordinator', 'assigned_section')
    search_fields = ('faculty__username', 'course__title', 'course_coordinator', 'section')
    readonly_fields = ('submission_date', 'updated_at')
    list_editable = ('status',)
    raw_id_fields = ('assigned_section',)
    
    def answer_count(self, obj):
        return obj.answers.count()
    answer_count.short_description = 'Answers'

@admin.register(FormAnswer)
class FormAnswerAdmin(admin.ModelAdmin):
    list_display = ('submission', 'question', 'answer_preview')
    list_filter = ('question__form',)
    search_fields = ('answer_text', 'submission__faculty__username')
    
    def answer_preview(self, obj):
        if obj.answer_text:
            return obj.answer_text[:50] + '...' if len(obj.answer_text) > 50 else obj.answer_text
        elif obj.answer_data:
            return 'Structured data'
        return 'No answer'
    answer_preview.short_description = 'Answer'

@admin.register(CourseOutline)
class CourseOutlineAdmin(admin.ModelAdmin):
    list_display = ('course', 'faculty', 'version', 'status', 'is_current', 'created_at')
    list_filter = ('status', 'is_current', 'course__department')
    search_fields = ('course__code', 'faculty__username', 'title')
    readonly_fields = ('created_at', 'updated_at', 'submitted_at', 'approved_at')
    list_editable = ('status', 'is_current')

@admin.register(AnalyticsCache)
class AnalyticsCacheAdmin(admin.ModelAdmin):
    list_display = ('analytics_type', 'form', 'course', 'generated_at')
    list_filter = ('analytics_type', 'generated_at')
    readonly_fields = ('generated_at',)