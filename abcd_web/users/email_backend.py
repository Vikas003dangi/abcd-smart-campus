import socket
import logging
import smtplib
from django.core.mail.backends.smtp import EmailBackend

logger = logging.getLogger(__name__)


class IPv4EmailBackend(EmailBackend):
    """
    High-Performance, Cloud-Hardened IPv4 SMTP Email Backend for Render, Docker, & AWS.
    1. Forces IPv4 socket connections (AF_INET) to prevent IPv6 [Errno 101] Network is unreachable errors on Linux cloud hosts.
    2. Works seamlessly with Port 465 SSL (recommended) or Port 587 STARTTLS.
    3. Dual-port auto-fallback: if Port 465 fails (timeout/firewall), attempts Port 587 STARTTLS (and vice-versa).
    4. Prevents socket hangs with an explicit timeout.
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
            logger.warning(f"[IPv4EmailBackend] Primary connection to SMTP {self.host}:{self.port} failed ({e}). Attempting dual-port fallback...")
            # Fallback 1: If primary was port 465 SSL, try port 587 with STARTTLS
            if self.port == 465 or self.use_ssl:
                try:
                    conn = smtplib.SMTP(self.host, 587, timeout=self.timeout)
                    conn.ehlo()
                    conn.starttls()
                    conn.ehlo()
                    if self.username and self.password:
                        conn.login(self.username, self.password)
                    self.connection = conn
                    logger.info("[IPv4EmailBackend] Fallback to Port 587 STARTTLS succeeded!")
                    return True
                except Exception as fb_err:
                    logger.error(f"[IPv4EmailBackend] Fallback to Port 587 failed: {fb_err}")
            # Fallback 2: If primary was port 587 TLS, try port 465 SSL
            elif self.port == 587 or self.use_tls:
                try:
                    conn = smtplib.SMTP_SSL(self.host, 465, timeout=self.timeout)
                    if self.username and self.password:
                        conn.login(self.username, self.password)
                    self.connection = conn
                    logger.info("[IPv4EmailBackend] Fallback to Port 465 SSL succeeded!")
                    return True
                except Exception as fb_err:
                    logger.error(f"[IPv4EmailBackend] Fallback to Port 465 failed: {fb_err}")

            if not self.fail_silently:
                raise e
            return False
        finally:
            socket.getaddrinfo = original_getaddrinfo
