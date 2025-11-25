from django.db import models
from django.contrib.auth.models import AbstractUser

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
        # Ensure only one active form at a time
        if self.status == self.STATUS_ACTIVE:
            # Deactivate other forms
            CCRForm.objects.filter(status=self.STATUS_ACTIVE).exclude(id=self.id).update(status=self.STATUS_INACTIVE)
        super().save(*args, **kwargs)


class CCRSubmission(models.Model):
    ccr_form = models.ForeignKey(CCRForm, on_delete=models.CASCADE)
    faculty = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    
    # Basic course information
    course_code_title = models.CharField(max_length=300)
    course_coordinator = models.CharField(max_length=200)
    
    # Questions
    q1_topics_included = models.TextField(verbose_name="HEC topics coverage")
    q2_topics_adjustments = models.TextField(verbose_name="Topics to add/remove")
    q3_week_distribution = models.TextField(verbose_name="Week-wise distribution")
    q4_books_relevance = models.TextField(verbose_name="Textbook relevance")
    q5_prerequisite_course = models.TextField(verbose_name="Prerequisite course")
    
    # CLO Review - CLO 1 to 4
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
    
    # CLO Domain, Level and Mapping
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
    
    # Group members
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