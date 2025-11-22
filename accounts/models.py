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