from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, Department

class UserRegisterForm(UserCreationForm):
    role = forms.ChoiceField(choices=User.ROLE_CHOICES, required=True)
    department = forms.CharField(max_length=200, required=False)
    designation = forms.CharField(max_length=200, required=False)
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "role", "department", "designation", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Get departments for dropdown
        departments = Department.objects.all()
        department_choices = [(dept.name, dept.name) for dept in departments]
        department_choices.insert(0, ('', 'Select Department'))
        
        # Update department field to be a ChoiceField
        self.fields['department'] = forms.ChoiceField(
            choices=department_choices,
            required=False,
            widget=forms.Select(attrs={
                'class': 'w-full border rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400'
            })
        )

        # shared classes for inputs
        base_classes = "w-full border rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"

        # configure widgets & placeholders
        self.fields["username"].widget.attrs.update({
            "class": base_classes,
            "placeholder": "username",
            "autocomplete": "username",
        })
        self.fields["email"].widget.attrs.update({
            "class": base_classes,
            "placeholder": "you@example.com",
            "inputmode": "email",
            "autocomplete": "email",
        })
        self.fields["role"].widget.attrs.update({
            "class": base_classes,
        })
        self.fields["designation"].widget.attrs.update({
            "class": base_classes,
            "placeholder": "Designation (optional)",
        })
        self.fields["password1"].widget.attrs.update({
            "class": base_classes,
            "placeholder": "at least 8 characters",
            "autocomplete": "new-password",
        })
        self.fields["password2"].widget.attrs.update({
            "class": base_classes,
            "placeholder": "confirm password",
            "autocomplete": "new-password",
        })

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.role = self.cleaned_data['role']
        user.department = self.cleaned_data.get('department', '')
        user.designation = self.cleaned_data.get('designation', '')
        
        if commit:
            user.save()
        return user