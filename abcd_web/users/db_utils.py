# users/db_utils.py
"""
Database Utilities for Production-Grade SQLite Handling
========================================================
Handles:
- Database lock retry logic with exponential backoff
- Transaction management for concurrent requests
- Thread-safe operations

For SQLite in production scenarios with potential concurrent access.
"""

import time
import logging
import functools
from contextlib import contextmanager
from django.db import connection, transaction, OperationalError
from django.http import JsonResponse

logger = logging.getLogger(__name__)

# =========================================================================
# CONFIGURATION
# =========================================================================
DB_LOCK_CONFIG = {
    'max_retries': 5,
    'initial_delay': 0.1,  # 100ms
    'max_delay': 2.0,      # 2 seconds max
    'backoff_factor': 2.0,
}


# =========================================================================
# RETRY DECORATOR FOR DATABASE OPERATIONS
# =========================================================================
def retry_on_db_lock(max_retries=None, initial_delay=None, max_delay=None, backoff_factor=None):
    """
    Decorator that retries a function when a database lock error occurs.
    
    Uses exponential backoff to avoid hammering the database.
    
    Usage:
        @retry_on_db_lock()
        def my_view(request):
            # ... database operations
            pass
    
    Or with custom settings:
        @retry_on_db_lock(max_retries=10, initial_delay=0.2)
        def my_view(request):
            pass
    """
    max_retries = max_retries or DB_LOCK_CONFIG['max_retries']
    initial_delay = initial_delay or DB_LOCK_CONFIG['initial_delay']
    max_delay = max_delay or DB_LOCK_CONFIG['max_delay']
    backoff_factor = backoff_factor or DB_LOCK_CONFIG['backoff_factor']
    
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                    
                except OperationalError as e:
                    error_message = str(e).lower()
                    
                    # Check if it's a database lock error
                    if 'database is locked' in error_message or 'locked' in error_message:
                        last_exception = e
                        
                        if attempt < max_retries:
                            logger.warning(
                                f"Database locked on attempt {attempt + 1}/{max_retries + 1} "
                                f"for {func.__name__}. Retrying in {delay:.2f}s..."
                            )
                            time.sleep(delay)
                            delay = min(delay * backoff_factor, max_delay)
                        else:
                            logger.error(
                                f"Database lock persisted after {max_retries + 1} attempts "
                                f"for {func.__name__}. Giving up."
                            )
                            raise
                    else:
                        # Not a lock error, re-raise immediately
                        raise
            
            # Should not reach here, but just in case
            if last_exception:
                raise last_exception
        
        return wrapper
    return decorator


# =========================================================================
# CONTEXT MANAGER FOR SAFE TRANSACTIONS
# =========================================================================
@contextmanager
def safe_atomic_transaction(max_retries=None, initial_delay=None):
    """
    Context manager for safe database transactions with retry logic.
    
    Usage:
        with safe_atomic_transaction():
            student.status = 'admitted'
            student.save()
            seat.status = 'occupied'
            seat.save()
    
    If a database lock occurs, it will retry with exponential backoff.
    """
    max_retries = max_retries or DB_LOCK_CONFIG['max_retries']
    initial_delay = initial_delay or DB_LOCK_CONFIG['initial_delay']
    max_delay = DB_LOCK_CONFIG['max_delay']
    backoff_factor = DB_LOCK_CONFIG['backoff_factor']
    
    delay = initial_delay
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            with transaction.atomic():
                yield
                return  # Success - exit the context manager
                
        except OperationalError as e:
            error_message = str(e).lower()
            
            if 'database is locked' in error_message or 'locked' in error_message:
                last_exception = e
                
                if attempt < max_retries:
                    logger.warning(
                        f"Database locked in atomic transaction (attempt {attempt + 1}/"
                        f"{max_retries + 1}). Retrying in {delay:.2f}s..."
                    )
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)
                else:
                    logger.error(
                        f"Database lock persisted after {max_retries + 1} attempts. "
                        "Giving up."
                    )
                    raise
            else:
                # Not a lock error - re-raise immediately
                raise
    
    if last_exception:
        raise last_exception


# =========================================================================
# VIEW DECORATOR FOR SAFE DATABASE OPERATIONS
# =========================================================================
def safe_db_operation(view_func):
    """
    Decorator for views that wraps the entire view in retry logic.
    
    Usage:
        @safe_db_operation
        @login_required
        def my_view(request):
            # ... database operations
            pass
    
    Note: Place this decorator AFTER authentication decorators.
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        delay = DB_LOCK_CONFIG['initial_delay']
        max_retries = DB_LOCK_CONFIG['max_retries']
        max_delay = DB_LOCK_CONFIG['max_delay']
        backoff_factor = DB_LOCK_CONFIG['backoff_factor']
        
        for attempt in range(max_retries + 1):
            try:
                return view_func(request, *args, **kwargs)
                
            except OperationalError as e:
                error_message = str(e).lower()
                
                if 'database is locked' in error_message:
                    if attempt < max_retries:
                        logger.warning(
                            f"Database locked in view {view_func.__name__} "
                            f"(attempt {attempt + 1}/{max_retries + 1}). "
                            f"Retrying in {delay:.2f}s..."
                        )
                        time.sleep(delay)
                        delay = min(delay * backoff_factor, max_delay)
                    else:
                        logger.error(
                            f"Database lock persisted after {max_retries + 1} attempts "
                            f"in view {view_func.__name__}."
                        )
                        # Return user-friendly error response
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            return JsonResponse({
                                'status': 'error',
                                'message': 'Server is busy. Please try again in a moment.',
                                'code': 'DATABASE_BUSY'
                            }, status=503)
                        else:
                            from django.contrib import messages
                            messages.error(
                                request, 
                                'The server is processing many requests. '
                                'Please try again in a moment.'
                            )
                            from django.shortcuts import redirect
                            return redirect('/')
                else:
                    raise
        
        # Should not reach here
        raise OperationalError("Database operation failed after max retries")
    
    return wrapper


# =========================================================================
# REQUEST DEDUPLICATION
# =========================================================================
from django.core.cache import cache
import hashlib


from django.http.request import RawPostDataException


def get_request_hash(request):
    """Generate a unique hash for a request to detect duplicates."""
    body_str = ''
    try:
        if hasattr(request, 'POST') and request.POST:
            body_str = '&'.join([f"{k}={v}" for k, v in sorted(request.POST.items())])
        elif hasattr(request, 'FILES') and request.FILES:
            body_str = '&'.join([f"file_{k}={v.name}" for k, v in sorted(request.FILES.items())])
        else:
            try:
                body_str = request.body.decode('utf-8', errors='ignore') if request.body else ''
            except RawPostDataException:
                body_str = ''
    except Exception:
        body_str = ''

    components = [
        str(request.user.id) if (hasattr(request, 'user') and request.user and request.user.is_authenticated) else 'anonymous',
        getattr(request, 'path', ''),
        getattr(request, 'method', ''),
        body_str,
    ]
    content = '|'.join(components)
    return hashlib.sha256(content.encode()).hexdigest()


def deduplicate_request(timeout=5):
    """
    Decorator that prevents duplicate requests within a time window.
    
    Usage:
        @deduplicate_request(timeout=5)  # 5 second window
        @login_required
        def my_view(request):
            pass
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
                return view_func(request, *args, **kwargs)
            
            request_hash = get_request_hash(request)
            cache_key = f'dedupe_{view_func.__name__}_{request_hash}'
            
            # Check if this request was recently processed
            if cache.get(cache_key):
                logger.warning(
                    f"Duplicate request detected for {view_func.__name__} "
                    f"from user {request.user}. Ignoring."
                )
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'status': 'duplicate',
                        'message': 'This action is already being processed.',
                        'code': 'DUPLICATE_REQUEST'
                    }, status=429)
                else:
                    from django.contrib import messages
                    messages.warning(request, 'This action is already being processed.')
                    from django.shortcuts import redirect
                    return redirect('/')
            
            # Mark this request as being processed
            cache.set(cache_key, True, timeout)
            
            try:
                return view_func(request, *args, **kwargs)
            finally:
                # Clear the deduplication lock after completion
                # (but leave it for a short time to prevent rapid re-submission)
                cache.set(cache_key, True, 2)
        
        return wrapper
    return decorator


# =========================================================================
# COMBINE ALL PROTECTIONS
# =========================================================================
def production_safe_view(timeout=5, max_retries=None):
    """
    Combined decorator that applies all production safety measures:
    - Request deduplication
    - Database lock retry
    
    Usage:
        @production_safe_view(timeout=5)
        @login_required
        @transaction.atomic
        def my_critical_view(request):
            pass
    """
    def decorator(view_func):
        @deduplicate_request(timeout=timeout)
        @safe_db_operation
        @functools.wraps(view_func)
        def wrapper(*args, **kwargs):
            return view_func(*args, **kwargs)
        return wrapper
    return decorator


# =========================================================================
# GLOBAL CRASH PREVENTION MIDDLEWARE
# =========================================================================
class GlobalCrashPreventionMiddleware:
    """
    Middleware that prevents server crashes from unhandled database lock errors,
    concurrency collisions, or uncaught exceptions during high traffic.
    
    1. Automatic Database Lock Retry: Automatically retries request handling on SQLite lock.
    2. Zero-Crash Exception Trap: Traps any unexpected server-side exception, rolls back
       active DB transactions safely, and returns a graceful user response instead of 500 crashes.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        max_retries = 5
        initial_delay = 0.05
        delay = initial_delay
        backoff_factor = 2.0
        max_delay = 1.0

        for attempt in range(max_retries + 1):
            try:
                return self.get_response(request)
            except OperationalError as e:
                err_str = str(e).lower()
                if ('database is locked' in err_str or 'locked' in err_str) and attempt < max_retries:
                    logger.warning(
                        f"[GlobalCrashPrevention] Database locked on attempt {attempt + 1}/{max_retries + 1} "
                        f"for path {request.path}. Retrying in {delay:.2f}s..."
                    )
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)
                else:
                    logger.error(f"[GlobalCrashPrevention] Database lock or operational error at {request.path}: {e}", exc_info=True)
                    return self._handle_graceful_error(request, e)
            except Exception as e:
                logger.error(f"[GlobalCrashPrevention] Unhandled exception caught at {request.path}: {e}", exc_info=True)
                return self._handle_graceful_error(request, e)

    def _handle_graceful_error(self, request, exception):
        # Roll back active transaction if connection is in an error state
        try:
            from django.db import connection
            if connection.in_atomic_block:
                transaction.set_rollback(True)
        except Exception:
            pass

        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')
        if is_ajax:
            return JsonResponse({
                'status': 'error',
                'message': 'The server experienced a temporary busy state. Please try your request again.',
                'code': 'SERVER_LOCK_RECOVERED'
            }, status=503)

        from django.contrib import messages
        from django.shortcuts import redirect
        try:
            messages.error(request, "The server is currently processing high activity. Your request has been safely protected. Please try again.")
        except Exception:
            pass

        referer = request.META.get('HTTP_REFERER')
        if referer and referer.startswith(request.build_absolute_uri('/')[:-1]):
            return redirect(referer)
        return redirect('/')

