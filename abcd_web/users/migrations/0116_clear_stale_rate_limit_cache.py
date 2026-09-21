# Generated to clear stale OTP verification rate limit rows from database cache
from django.db import migrations
import logging

logger = logging.getLogger(__name__)


def clear_stale_cache_entries(apps, schema_editor):
    from django.db import connection, transaction
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = 'guidy_presence_cache'
                    );
                """)
                table_exists = cursor.fetchone()[0]
                if table_exists:
                    cursor.execute(
                        "DELETE FROM guidy_presence_cache WHERE cache_key LIKE '%verification_daily%' OR cache_key LIKE '%reg_otp%';"
                    )
                    logger.info("Cleared stale verification rate limit keys from guidy_presence_cache.")
    except Exception as e:
        logger.warning(f"Note: guidy_presence_cache cleanup skipped or table does not exist yet: {e}")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0115_launch_clean_slate_reset'),
    ]

    operations = [
        migrations.RunPython(clear_stale_cache_entries, noop),
    ]
