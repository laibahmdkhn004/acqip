from django import forms
from django.contrib.auth.forms import (
    UserCreationForm,
    PasswordResetForm,
    SetPasswordForm,
)
from django.core.mail import EmailMultiAlternatives
from django.template import loader
from .models import User, Department

AUTH_INPUT_CLASSES = (
    "w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-sm "
    "focus:outline-none focus:ring-2 focus:ring-purple-500"
)

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


class UserPasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "class": AUTH_INPUT_CLASSES,
                "placeholder": "Enter your registered email",
                "autocomplete": "email",
            }
        ),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        matching_users = list(self.get_users(email))
        if not matching_users:
            raise forms.ValidationError(
                "No account found with this email address."
            )
        return email

    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        # Django's default send_mail logs SMTP failures and continues, which
        # incorrectly shows the "check your email" success page. Re-raise so
        # the view can display an error instead.
        subject = loader.render_to_string(subject_template_name, context)
        subject = "".join(subject.splitlines())
        body = loader.render_to_string(email_template_name, context)

        email_message = EmailMultiAlternatives(subject, body, from_email, [to_email])
        if html_email_template_name is not None:
            html_email = loader.render_to_string(html_email_template_name, context)
            email_message.attach_alternative(html_email, "text/html")

        sent_count = email_message.send(fail_silently=False)
        if sent_count == 0:
            raise forms.ValidationError(
                "Unable to send the password reset email. Please try again later."
            )

    def save(self, *args, **kwargs):
        try:
            super().save(*args, **kwargs)
        except forms.ValidationError:
            raise
        except Exception as email_error:
            raise forms.ValidationError(
                "Unable to send the password reset email. Please try again later."
            ) from email_error


class UserSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].widget.attrs.update(
            {
                "class": AUTH_INPUT_CLASSES,
                "placeholder": "Enter new password",
                "autocomplete": "new-password",
            }
        )
        self.fields["new_password2"].widget.attrs.update(
            {
                "class": AUTH_INPUT_CLASSES,
                "placeholder": "Confirm new password",
                "autocomplete": "new-password",
            }
        )