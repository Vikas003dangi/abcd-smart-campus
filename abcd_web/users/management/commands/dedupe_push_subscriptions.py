# users/management/commands/dedupe_push_subscriptions.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db.models import Count
from users.models import PushSubscription

User = get_user_model()


class Command(BaseCommand):
    help = "Deduplicates and cleans up PushSubscription rows. Enforces at most 2 active subscriptions per user (DRY RUN by default)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            default=False,
            help='Execute the deletion of stale/duplicate push subscriptions. Default is DRY RUN.'
        )
        parser.add_argument(
            '--user',
            type=str,
            default=None,
            help='Optionally limit deduplication to a specific username or email.'
        )

    def handle(self, *args, **options):
        apply_mode = options.get('apply', False)
        target_user = options.get('user')

        self.stdout.write(self.style.NOTICE(
            f"=== PushSubscription Deduplication ({'APPLY MODE' if apply_mode else 'DRY RUN - Read Only'}) ==="
        ))

        user_qs = User.objects.annotate(sub_count=Count('pushsubscription')).filter(sub_count__gt=2)
        if target_user:
            user_qs = user_qs.filter(username=target_user) | user_qs.filter(email=target_user)

        total_users_examined = user_qs.count()
        total_stale_to_delete = 0
        deleted_ids = []

        # 1. Check for excess subscriptions per user (> 2)
        for u in user_qs:
            subs = list(PushSubscription.objects.filter(user=u).order_by('-id'))
            if len(subs) <= 2:
                continue

            # Prioritize keeping 1 newest TWA + 1 newest Browser/Desktop if available
            twa_subs = [s for s in subs if getattr(s, 'client_type', None) == 'twa']
            other_subs = [s for s in subs if getattr(s, 'client_type', None) != 'twa']

            to_keep = []
            if twa_subs:
                to_keep.append(twa_subs[0])
            if other_subs:
                to_keep.append(other_subs[0])

            # Fill up to 2 newest total
            for s in subs:
                if len(to_keep) >= 2:
                    break
                if s not in to_keep:
                    to_keep.append(s)

            keep_ids = {s.id for s in to_keep}
            stale_for_user = [s.id for s in subs if s.id not in keep_ids]

            total_stale_to_delete += len(stale_for_user)
            deleted_ids.extend(stale_for_user)

            self.stdout.write(
                f" - User '{u.username}' (ID: {u.id}): {len(subs)} total subs -> keeping IDs {list(keep_ids)}, deleting stale IDs {stale_for_user}"
            )

        # 2. Check for duplicate endpoints across any user (safety guard)
        seen_endpoints = set()
        endpoint_dupe_ids = []
        for sub in PushSubscription.objects.order_by('-id'):
            if sub.endpoint in seen_endpoints:
                if sub.id not in deleted_ids:
                    endpoint_dupe_ids.append(sub.id)
            else:
                seen_endpoints.add(sub.endpoint)

        if endpoint_dupe_ids:
            total_stale_to_delete += len(endpoint_dupe_ids)
            deleted_ids.extend(endpoint_dupe_ids)
            self.stdout.write(self.style.WARNING(
                f"Found {len(endpoint_dupe_ids)} duplicate endpoint subscriptions: {endpoint_dupe_ids}"
            ))

        # 3. Execution or Dry Run Summary
        all_stale_ids = sorted(list(set(deleted_ids)))
        if not all_stale_ids:
            self.stdout.write(self.style.SUCCESS("All users comply with the max-2 subscription policy. Nothing to clean."))
            return

        if apply_mode:
            count, _ = PushSubscription.objects.filter(id__in=all_stale_ids).delete()
            self.stdout.write(self.style.SUCCESS(
                f"[APPLY SUCCESS] Deleted {count} stale/duplicate PushSubscription rows."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"[DRY RUN COMPLETE] {len(all_stale_ids)} stale subscription(s) identified for deletion across {total_users_examined} user(s). "
                f"No changes were made to the database. Re-run with --apply to execute."
            ))
