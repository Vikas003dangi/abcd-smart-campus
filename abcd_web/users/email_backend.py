import socket
import logging
from django.core.mail.backends.smtp import EmailBackend

logger = logging.getLogger(__name__)


class IPv4EmailBackend(EmailBackend):
    """
    High-Performance, Cloud-Hardened IPv4 SMTP Email Backend for Render, Docker, & AWS.
    1. Forces IPv4 socket connections (AF_INET) to prevent IPv6 [Errno 101] Network is unreachable errors on Linux cloud hosts.
    2. Works seamlessly with Port 465 SSL (recommended) or Port 587 STARTTLS.
    3. Prevents socket hangs with an explicit timeout.
    """

    def __init__(self, *args, **kwargs):
        if 'timeout' not in kwargs or kwargs['timeout'] is None or kwargs['timeout'] > 15:
            kwargs['timeout'] = 10
        super().__init__(*args, **kwargs)

    def open(self):
        if self.connection:
            return False

        # Hook socket.getaddrinfo to strictly return IPv4 addresses (socket.AF_INET)
        original_getaddrinfo = socket.getaddrinfo

        def ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

        socket.getaddrinfo = ipv4_getaddrinfo
        try:
            return super().open()
        except Exception as e:
            logger.error(f"[IPv4EmailBackend] Failed to connect to SMTP server {self.host}:{self.port} - {e}")
            if not self.fail_silently:
                raise
            return False
        finally:
            socket.getaddrinfo = original_getaddrinfo
