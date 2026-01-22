from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    ROLE_ADMIN = "admin"
    ROLE_FACULTY = "faculty"
    ROLE_CRC_MEMBER = "crc_member"
    ROLE_CHOICES = [
        (ROLE_ADMIN, "Admin"),
        (ROLE_FACULTY, "Faculty"),
        (ROLE_CRC_MEMBER, "CRC Member"),
    ]
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default=ROLE_FACULTY)
    department = models.CharField(max_length=200, blank=True, null=True)
    designation = models.CharField(max_length=200, blank=True, null=True)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class Department(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20, unique=True ,null=True, blank=True)
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
    faculty = models.ManyToManyField(User, through='CourseFaculty', related_name='assigned_courses', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.code} - {self.title}"


class CourseFaculty(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    faculty = models.ForeignKey(User, on_delete=models.CASCADE)
    is_coordinator = models.BooleanField(default=False)
    section = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('course', 'faculty')
    
    def __str__(self):
        return f"{self.faculty.username} - {self.course.code} (Coordinator: {self.is_coordinator})"


class DynamicForm(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_INACTIVE = "inactive"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_INACTIVE, "Inactive"),
    ]
    
    FORM_TYPES = [
        ('ccr', 'CCR Form (Course Coordinators)'),
        ('crr', 'CRR Form (Regular Faculty)'),
        
    ]
    
    name = models.CharField(max_length=200, default="Dynamic Form")
    description = models.TextField(blank=True)
    form_type = models.CharField(max_length=20, choices=FORM_TYPES, default='crr')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_INACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Dynamic Form"
        verbose_name_plural = "Dynamic Forms"
    
    def __str__(self):
        return f"{self.name} ({self.get_form_type_display()})"


class FormQuestion(models.Model):
    QUESTION_TYPES = [
        ('text', 'Text Input'),
        ('textarea', 'Text Area'),
        ('checkbox', 'Checkbox'),
        ('select', 'Dropdown'),
        ('radio', 'Radio Buttons'),
        ('section_header', 'Section Header'),
        ('file', 'File Upload'),
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


class DynamicFormSubmission(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED = "submitted"
    STATUS_APPROVED = "approved"
    STATUS_REVISION = "revision_requested"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REVISION, "Revision Requested"),
    ]
    
    dynamic_form = models.ForeignKey(DynamicForm, on_delete=models.CASCADE)
    faculty = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    
    course_code_title = models.CharField(max_length=300)
    course_coordinator = models.CharField(max_length=200, blank=True)
    is_coordinator = models.BooleanField(default=False)
    section = models.CharField(max_length=20, blank=True, null=True)
    
    submission_date = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    
    class Meta:
        unique_together = ['faculty', 'course', 'dynamic_form']
    
    def __str__(self):
        return f"Dynamic Submission by {self.faculty.username} for {self.course.code}"


class FormAnswer(models.Model):
    submission = models.ForeignKey(DynamicFormSubmission, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(FormQuestion, on_delete=models.CASCADE)
    answer_text = models.TextField(blank=True)
    answer_data = models.JSONField(blank=True, null=True, help_text="Structured data for complex answers")
    file_upload = models.FileField(upload_to='form_uploads/', blank=True, null=True)
    
    def __str__(self):
        return f"Answer for {self.question.question_text[:50]}"


class CourseOutline(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED = "submitted"
    STATUS_APPROVED = "approved"
    STATUS_REVISION = "revision_requested"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REVISION, "Revision Requested"),
    ]
    
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='outlines')
    faculty = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_outlines')
    version = models.IntegerField(default=1)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    content = models.TextField(blank=True, null=True, help_text="HTML content for course outline")
    file = models.FileField(upload_to='course_outlines/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    is_current = models.BooleanField(default=False, help_text="Is this the current official outline?")
    notes = models.TextField(blank=True, help_text="CRC notes or revision requests")
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-version']
        unique_together = ['course', 'faculty', 'version']
    
    def __str__(self):
        return f"Course Outline for {self.course.code} v{self.version}"


class AnalyticsCache(models.Model):
    form = models.ForeignKey(DynamicForm, on_delete=models.CASCADE, null=True, blank=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, null=True, blank=True)
    faculty = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, null=True, blank=True)
    
    analytics_type = models.CharField(max_length=50)
    data = models.JSONField()
    generated_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Analytics Caches"
    
    def __str__(self):
        return f"Analytics for {self.analytics_type}"