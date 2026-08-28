import socket
import smtplib
import logging
from django.core.mail.backends.smtp import EmailBackend

logger = logging.getLogger(__name__)

class IPv4EmailBackend(EmailBackend):
    """
    Robust SMTP Email Backend designed for cloud hosting containers (Render, Docker, AWS).
    
    Key Features:
    1. Forces IPv4 socket connections (AF_INET) to prevent [Errno 101] Network is unreachable
       caused when cloud hosts attempt unreachable IPv6 routing for smtp.gmail.com.
    2. Dual-Port Fallback: Tries Port 587 (STARTTLS) first, and automatically falls back to 
       Port 465 (SSL) if port 587 is blocked or times out.
    """

    def open(self):
        if self.connection:
            return False

        # Hook socket.getaddrinfo to strictly return IPv4 addresses (socket.AF_INET)
        original_getaddrinfo = socket.getaddrinfo

        def ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

        socket.getaddrinfo = ipv4_getaddrinfo

        try:
            # First attempt: standard configuration (usually port 587 with STARTTLS)
            return super().open()
        except Exception as primary_err:
            logger.warning(
                f"[IPv4EmailBackend] Primary connection to {self.host}:{self.port} failed: {primary_err}. "
                f"Attempting fallback to Port 465 SSL..."
            )
            try:
                # Fallback attempt: direct SSL connection on Port 465
                self.connection = smtplib.SMTP_SSL(
                    self.host,
                    465,
                    timeout=self.timeout
                )
                if self.username and self.password:
                    self.connection.login(self.username, self.password)
                logger.info(f"[IPv4EmailBackend] Successfully connected to {self.host}:465 via SSL fallback.")
                return True
            except Exception as fallback_err:
                logger.error(
                    f"[IPv4EmailBackend] Both primary ({self.port}) and fallback (465) connections failed. "
                    f"Primary error: {primary_err} | Fallback error: {fallback_err}"
                )
                if not self.fail_silently:
                    raise primary_err
                return False
        finally:
            # Always restore original socket.getaddrinfo
            socket.getaddrinfo = original_getaddrinfo
