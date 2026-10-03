import getpass
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Q

User = get_user_model()


class Command(BaseCommand):
    help = "Resets a superuser password interactively via getpass and clears all lockout cache counters."

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Username or email of the superuser account')

    def handle(self, *args, **options):
        identifier = options['username'].strip()

        user = User.objects.filter(
            Q(username__iexact=identifier) | Q(email__iexact=identifier)
        ).first()

        if not user:
            raise CommandError(f"User matching '{identifier}' was not found in the database.")

        if not user.is_superuser:
            self.stdout.write(self.style.WARNING(
                f"User '{user.username}' is not currently marked as superuser. Upgrading to superuser and staff..."
            ))
            user.is_superuser = True
            user.is_staff = True

        # Interactive, secure prompt: never accepted via command line args, never logged
        pwd1 = getpass.getpass(prompt=f"New password for {user.username}: ")
        if not pwd1:
            raise CommandError("Password cannot be blank.")

        pwd2 = getpass.getpass(prompt="Confirm new password: ")
        if pwd1 != pwd2:
            raise CommandError("Passwords do not match. Aborting reset.")

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
