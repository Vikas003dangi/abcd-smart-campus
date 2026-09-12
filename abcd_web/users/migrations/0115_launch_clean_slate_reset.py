# Generated for ABCD Smart Campus - Official Launch Reset
# Runs once via 'python manage.py migrate' and is recorded in django_migrations,
# guaranteeing it never runs again on future deploys.

from django.db import migrations
from django.contrib.auth.hashers import make_password
from decouple import config
import logging

logger = logging.getLogger(__name__)


def launch_clean_slate_reset(apps, schema_editor):
    # Historical Migration 0115 - Neutralized for Permanent Zero Data Loss.
    # All destructive mass deletions have been permanently removed to guarantee
    # that future deployments and migrations will NEVER wipe users, chats, todos, or records.
    pass


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0114_todotask_todo_u_cat_tr_cr_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(launch_clean_slate_reset, noop),
    ]
