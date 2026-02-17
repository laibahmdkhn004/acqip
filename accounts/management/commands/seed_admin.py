from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Create or update an admin user with email admin@gmail.com and password 12345678'

    def handle(self, *args, **options):
        email = 'admin@gmail.com'
        password = '12345678'
        username = 'admin'           # you can change this if desired
        role = 'admin'                # matches your User.ROLE_ADMIN

        try:
            # Try to get user by email (assuming email is unique in your system)
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'username': username,
                    'role': role,
                    'is_staff': True,
                    'is_superuser': True,   # optional: give full Django admin access
                    'is_active': True,
                }
            )

            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(self.style.SUCCESS(f'Admin user created: {email}'))
            else:
                # User exists – update password if needed
                if not user.check_password(password):
                    user.set_password(password)
                    user.save()
                    self.stdout.write(self.style.SUCCESS(f'Admin user password updated for {email}'))
                else:
                    self.stdout.write(self.style.WARNING(f'Admin user already exists with correct password: {email}'))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {e}'))