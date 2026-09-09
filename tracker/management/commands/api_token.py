from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    help = "Issue, rotate, or revoke an API token for a pre-created active user."

    def add_arguments(self, parser):
        parser.add_argument("username")
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--rotate", action="store_true")
        group.add_argument("--revoke", action="store_true")

    def handle(self, *args, **options):
        try:
            user = get_user_model().objects.get(
                username=options["username"], is_active=True
            )
        except get_user_model().DoesNotExist:
            raise CommandError("Active user not found.")
        if options["rotate"] or options["revoke"]:
            Token.objects.filter(user=user).delete()
        if options["revoke"]:
            self.stdout.write("Token revoked.")
        else:
            token, _ = Token.objects.get_or_create(user=user)
            self.stdout.write(token.key)
