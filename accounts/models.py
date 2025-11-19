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
