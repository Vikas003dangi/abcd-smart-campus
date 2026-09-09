from django.db import migrations
import logging

logger = logging.getLogger(__name__)

def purge_reminder_spam(apps, schema_editor):
    Notification = apps.get_model('users', 'Notification')
    TodoTask = apps.get_model('users', 'TodoTask')
    User = apps.get_model('auth', 'User')

    # 1. Delete all notifications matching 'wake up to reality' across system
    spam_q1, _ = Notification.objects.filter(title__icontains='wake up to reality').delete()
    spam_q2, _ = Notification.objects.filter(message__icontains='wake up to reality').delete()
    print(f"[Migration 0113] Deleted {spam_q1 + spam_q2} 'wake up to reality' spam notifications.")

    # 2. Target user vd19055@gmail.com / Vaku
    target_users = list(User.objects.filter(email__iexact='vd19055@gmail.com'))
    vaku = User.objects.filter(username__iexact='Vaku').first()
    if vaku and vaku not in target_users:
        target_users.append(vaku)

    for u in target_users:
        # Purge all alarm & reminder notifications flooded during the incident
        deleted_count, _ = Notification.objects.filter(
            user=u,
            category__in=['alarm', 'reminder']
        ).delete()
        print(f"[Migration 0113] Purged {deleted_count} alarm/reminder notifications for {u.username}")

        # Neutralize any stuck REMINDER tasks
        tasks = TodoTask.objects.filter(user=u, category='REMINDER')
        for t in tasks:
            t.is_done = True
            t.initial_notified = True
            meta = t.metadata if isinstance(t.metadata, dict) else {}
            meta['alarm_status'] = 'stopped'
            meta['next_retry_at'] = None
            t.metadata = meta
            t.save()
            print(f"[Migration 0113] Neutralized stuck reminder task {t.id} for {u.username}")

def noop(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('users', '0112_groupmessage_is_delivered'),
    ]

    operations = [
        migrations.RunPython(purge_reminder_spam, noop),
    ]
