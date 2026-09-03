from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'

    def ready(self):
        import sys
        if 'runserver' in sys.argv:
            from django.core.management import call_command
            try:
                call_command('makemigrations', 'users', interactive=False)
                call_command('migrate', 'users', interactive=False)
            except Exception as e:
                sys.stderr.write(f"Auto-migration error: {e}\n")

        # Register SQLite optimizations on connection creation
        from django.db.backends.signals import connection_created
        
        def configure_sqlite(sender, connection, **kwargs):
            if connection.vendor == 'sqlite':
                try:
                    cursor = connection.cursor()
                    cursor.execute('PRAGMA journal_mode=WAL;')
                    cursor.execute('PRAGMA synchronous=NORMAL;')
                    cursor.execute('PRAGMA busy_timeout=30000;')
                    cursor.execute('PRAGMA cache_size=-64000;')
                    cursor.execute('PRAGMA temp_store=MEMORY;')
                except Exception:
                    pass

        connection_created.connect(configure_sqlite)

        # Start 24/7 Embedded Background Scheduler Daemon
        try:
            from users.scheduler import start_background_scheduler
            start_background_scheduler()
        except Exception as e:
            sys.stderr.write(f"Scheduler auto-start error: {e}\n")
