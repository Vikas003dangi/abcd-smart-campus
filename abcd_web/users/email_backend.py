import socket
import smtplib
import logging
from django.core.mail.backends.smtp import EmailBackend

logger = logging.getLogger(__name__)

# Module-level cache to remember the working SMTP port (587 vs 465) across connections
_PREFERRED_PORT = None


class IPv4EmailBackend(EmailBackend):
    """
    High-Performance, Robust SMTP Email Backend for Cloud Hosting (Render, Docker, AWS).
    
    Key Features:
    1. Forces IPv4 socket connections (AF_INET) to prevent [Errno 101] Network is unreachable
       caused when cloud hosts attempt unreachable IPv6 routing for smtp.gmail.com.
    2. Intelligent Port Caching: Remembers the working port (587 TLS or 465 SSL) so all 
       subsequent emails connect in sub-seconds without repeating failed attempts.
    3. Fast-Failover: Connects with a tight 8-second timeout so users never experience buffering.
    """

    def __init__(self, *args, **kwargs):
        # Enforce an optimal timeout of 8 seconds if not explicitly set
        if 'timeout' not in kwargs or kwargs['timeout'] is None or kwargs['timeout'] > 10:
            kwargs['timeout'] = 8
        super().__init__(*args, **kwargs)

    def open(self):
        global _PREFERRED_PORT
        if self.connection:
            return False

        # Hook socket.getaddrinfo to strictly return IPv4 addresses (socket.AF_INET)
        original_getaddrinfo = socket.getaddrinfo

        def ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

        socket.getaddrinfo = ipv4_getaddrinfo

        try:
            # If Port 465 SSL was previously confirmed working, try 465 SSL directly
            if _PREFERRED_PORT == 465:
                try:
                    self.connection = smtplib.SMTP_SSL(
                        self.host,
                        465,
                        timeout=self.timeout
                    )
                    if self.username and self.password:
                        self.connection.login(self.username, self.password)
                    return True
                except Exception as e465:
                    logger.warning(f"[IPv4EmailBackend] Cached Port 465 failed: {e465}. Trying primary port {self.port}...")
                    _PREFERRED_PORT = None

            # Attempt primary port (standard 587 STARTTLS)
            try:
                result = super().open()
                if result:
                    _PREFERRED_PORT = self.port
                    return True
            except Exception as primary_err:
                logger.warning(
                    f"[IPv4EmailBackend] Primary connection to {self.host}:{self.port} failed: {primary_err}. "
                    f"Attempting fallback to Port 465 SSL..."
                )
                try:
                    self.connection = smtplib.SMTP_SSL(
                        self.host,
                        465,
                        timeout=self.timeout
                    )
                    if self.username and self.password:
                        self.connection.login(self.username, self.password)
                    _PREFERRED_PORT = 465
                    logger.info(f"[IPv4EmailBackend] Successfully connected to {self.host}:465 via SSL fallback.")
                    return True
                except Exception as fallback_err:
                    logger.error(
                        f"[IPv4EmailBackend] Both primary ({self.port}) and fallback (465) connections failed. "
                        f"Primary: {primary_err} | Fallback: {fallback_err}"
                    )
                    if not self.fail_silently:
                        raise primary_err
                    return False
        finally:
            # Always restore original socket.getaddrinfo
            socket.getaddrinfo = original_getaddrinfo
