from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User

class UserRegisterForm(UserCreationForm):
    role = forms.ChoiceField(choices=User.ROLE_CHOICES, required=True)

    class Meta:
        model = User
        fields = ("username", "email", "role", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
