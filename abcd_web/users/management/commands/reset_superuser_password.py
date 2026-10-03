import getpass
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.db.models import Q

User = get_user_model()


class Command(BaseCommand):
    help = "Resets a superuser password interactively via getpass and clears all lockout cache counters."

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username or email of the superuser account')
        parser.add_argument(
            '--promote',
            action='store_true',
            help='Allow promoting an existing non-superuser account to superuser after typing confirmation.'
        )

    def handle(self, *args, **options):
        identifier = options['username'].strip()
        allow_promote = options.get('promote', False)

        user = User.objects.filter(
            Q(username__iexact=identifier) | Q(email__iexact=identifier)
        ).first()

        if not user:
            raise CommandError(f"User matching '{identifier}' was not found in the database. Users cannot be created by this command.")

        if not user.is_superuser:
            if not allow_promote:
                raise CommandError(
                    f"User '{user.username}' exists but is not a superuser. "
                    f"To promote this user to superuser, re-run with the --promote flag."
                )

            confirm_username = input(
                f"User '{user.username}' is not a superuser. To confirm promotion to superuser, type the username '{user.username}': "
            ).strip()
            if confirm_username != user.username:
                raise CommandError("Username confirmation did not match. Aborting promotion.")

            self.stdout.write(self.style.WARNING(
                f"Promoting user '{user.username}' to superuser and staff..."
            ))
            user.is_superuser = True
            user.is_staff = True

        # Interactive, secure prompt with validation, min length 8, and re-prompt on failure
        # Never accepted via CLI arguments, never printed or logged
        max_attempts = 3
        pwd1 = None
        for attempt in range(1, max_attempts + 1):
            pwd_input = getpass.getpass(prompt=f"New password for {user.username}: ")
            if not pwd_input:
                self.stdout.write(self.style.ERROR("Password cannot be blank."))
                continue

            if len(pwd_input) < 8:
                self.stdout.write(self.style.ERROR("Password must be at least 8 characters long."))
                continue

            try:
                validate_password(pwd_input, user=user)
            except ValidationError as err:
                self.stdout.write(self.style.ERROR(f"Password validation failed: {'; '.join(err.messages)}"))
                continue

            pwd2 = getpass.getpass(prompt="Confirm new password: ")
            if pwd_input != pwd2:
                self.stdout.write(self.style.ERROR("Passwords do not match."))
                continue

            pwd1 = pwd_input
            break

        if not pwd1:
            raise CommandError(f"Failed to enter a valid password after {max_attempts} attempts. Aborting.")

        user.set_password(pwd1)
        user.save()

        # Clear cached lockout counters and rate limits for this user
        identifiers = {user.username, user.username.lower()}
        if user.email:
            identifiers.add(user.email)
            identifiers.add(user.email.lower())

        keys_to_clear = [f"login_attempts_{user.pk}"]
        for name in identifiers:
            keys_to_clear.extend([
                f"login_failed_user_{name}",
                f"login_lock_phase_user_{name}",
                f"login_lock_until_user_{name}",
            ])

        for key in keys_to_clear:
            cache.delete(key)

        self.stdout.write(self.style.SUCCESS(
            f"Successfully updated password and cleared lockout cache for superuser '{user.username}' ({user.email})."
        ))
