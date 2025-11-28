from django.db import models
from django.contrib.auth.models import AbstractUser
import json

class User(AbstractUser):
    ROLE_ADMIN = "admin"
    ROLE_COLLABORATOR = "course_collaborator"
    ROLE_FACULTY = "faculty"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_COLLABORATOR, "Course Collaborator"),
        (ROLE_FACULTY, "Faculty"),
    ]
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default=ROLE_FACULTY)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class Department(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class Course(models.Model):
    title = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='courses')
    credits = models.IntegerField(default=3)
    faculty = models.ManyToManyField(User, related_name='assigned_courses', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.code} - {self.title}"


class Form(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name


class CCRForm(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_INACTIVE, "Inactive"),
    ]
    
    name = models.CharField(max_length=200, default="CCR Form", unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_INACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "CCR Form"
        verbose_name_plural = "CCR Forms"
    
    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        if self.status == self.STATUS_ACTIVE:
            CCRForm.objects.filter(status=self.STATUS_ACTIVE).exclude(id=self.id).update(status=self.STATUS_INACTIVE)
        super().save(*args, **kwargs)


# Dynamic Form Models
class DynamicForm(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_INACTIVE, "Inactive"),
    ]
    
    name = models.CharField(max_length=200, default="Dynamic CCR Form")
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_INACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Dynamic Form"
        verbose_name_plural = "Dynamic Forms"
    
    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        if self.status == self.STATUS_ACTIVE:
            DynamicForm.objects.filter(status=self.STATUS_ACTIVE).exclude(id=self.id).update(status=self.STATUS_INACTIVE)
        super().save(*args, **kwargs)


class FormQuestion(models.Model):
    QUESTION_TYPES = [
        ('text', 'Text Input'),
        ('textarea', 'Text Area'),
        ('checkbox', 'Checkbox'),
        ('select', 'Dropdown'),
        ('radio', 'Radio Buttons'),
        ('section_header', 'Section Header'),
       
    ]
    
    form = models.ForeignKey(DynamicForm, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='text')
    order = models.IntegerField(default=0)
    required = models.BooleanField(default=True)
    options = models.TextField(blank=True, help_text="For select/radio types, provide options separated by commas")
    config = models.JSONField(blank=True, null=True, help_text="JSON configuration for complex question types")
    help_text = models.TextField(blank=True, help_text="Additional help text for this question")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'created_at']
    
    def __str__(self):
        return f"{self.form.name} - {self.question_text[:50]}"
    
    def get_config(self):
        if self.config:
            return self.config
        return {}


class DynamicFormSubmission(models.Model):
    dynamic_form = models.ForeignKey(DynamicForm, on_delete=models.CASCADE)
    faculty = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    
    course_code_title = models.CharField(max_length=300)
    course_coordinator = models.CharField(max_length=200)
    
    submission_date = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['faculty', 'course', 'dynamic_form']
    
    def __str__(self):
        return f"Dynamic Submission by {self.faculty.username} for {self.course.code}"


class FormAnswer(models.Model):
    submission = models.ForeignKey(DynamicFormSubmission, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(FormQuestion, on_delete=models.CASCADE)
    answer_text = models.TextField(blank=True)
    answer_data = models.JSONField(blank=True, null=True, help_text="Structured data for complex answers")
    
    def __str__(self):
        return f"Answer for {self.question.question_text[:50]}"


# Keep original CCRSubmission for backward compatibility
class CCRSubmission(models.Model):
    ccr_form = models.ForeignKey(CCRForm, on_delete=models.CASCADE)
    faculty = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    
    course_code_title = models.CharField(max_length=300)
    course_coordinator = models.CharField(max_length=200)
    
    q1_topics_included = models.TextField(verbose_name="HEC topics coverage")
    q2_topics_adjustments = models.TextField(verbose_name="Topics to add/remove")
    q3_week_distribution = models.TextField(verbose_name="Week-wise distribution")
    q4_books_relevance = models.TextField(verbose_name="Textbook relevance")
    q5_prerequisite_course = models.TextField(verbose_name="Prerequisite course")
    
    clo1_student_centered = models.BooleanField(default=False)
    clo1_measurable = models.BooleanField(default=False)
    clo1_achievable = models.BooleanField(default=False)
    clo1_correct_verb = models.BooleanField(default=False)
    
    clo2_student_centered = models.BooleanField(default=False)
    clo2_measurable = models.BooleanField(default=False)
    clo2_achievable = models.BooleanField(default=False)
    clo2_correct_verb = models.BooleanField(default=False)
    
    clo3_student_centered = models.BooleanField(default=False)
    clo3_measurable = models.BooleanField(default=False)
    clo3_achievable = models.BooleanField(default=False)
    clo3_correct_verb = models.BooleanField(default=False)
    
    clo4_student_centered = models.BooleanField(default=False)
    clo4_measurable = models.BooleanField(default=False)
    clo4_achievable = models.BooleanField(default=False)
    clo4_correct_verb = models.BooleanField(default=False)
    
    clo1_domain = models.CharField(max_length=100, blank=True)
    clo1_level = models.CharField(max_length=100, blank=True)
    clo1_ga_mapping = models.CharField(max_length=100, blank=True)
    
    clo2_domain = models.CharField(max_length=100, blank=True)
    clo2_level = models.CharField(max_length=100, blank=True)
    clo2_ga_mapping = models.CharField(max_length=100, blank=True)
    
    clo3_domain = models.CharField(max_length=100, blank=True)
    clo3_level = models.CharField(max_length=100, blank=True)
    clo3_ga_mapping = models.CharField(max_length=100, blank=True)
    
    clo4_domain = models.CharField(max_length=100, blank=True)
    clo4_level = models.CharField(max_length=100, blank=True)
    clo4_ga_mapping = models.CharField(max_length=100, blank=True)
    
    group_member_1 = models.CharField(max_length=200, blank=True)
    group_member_2 = models.CharField(max_length=200, blank=True)
    group_member_3 = models.CharField(max_length=200, blank=True)
    group_member_4 = models.CharField(max_length=200, blank=True)
    
    submission_date = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['faculty', 'course', 'ccr_form']
    
    def __str__(self):
        return f"CCR Submission by {self.faculty.username} for {self.course.code}"