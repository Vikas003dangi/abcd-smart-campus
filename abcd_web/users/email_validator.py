# users/email_validator.py

import re
import socket
import logging
import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

# RFC 5322 simplified pattern for reliable syntax validation
EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+$'
)

# Common typo mappings for popular email providers
DOMAIN_TYPO_MAP = {
    # Gmail typos
    'gmial.com': 'gmail.com',
    'gmaill.com': 'gmail.com',
    'gamil.com': 'gmail.com',
    'gmai.com': 'gmail.com',
    'gmal.com': 'gmail.com',
    'gmaul.com': 'gmail.com',
    'gmeil.com': 'gmail.com',
    'gml.com': 'gmail.com',
    'gmaik.com': 'gmail.com',
    'gmaio.com': 'gmail.com',
    'gmail.co': 'gmail.com',
    'gmail.con': 'gmail.com',
    'gmail.cm': 'gmail.com',
    'gmail.cpm': 'gmail.com',
    'gmail.om': 'gmail.com',
    'gmail.comm': 'gmail.com',
    'gmai.co.in': 'gmail.com',
    'gmail.co.in': 'gmail.com',
    
    # Yahoo typos
    'yaho.com': 'yahoo.com',
    'yahooo.com': 'yahoo.com',
    'yaho.co': 'yahoo.com',
    'yaho.in': 'yahoo.in',
    'yaho.co.in': 'yahoo.co.in',
    'ymail.con': 'ymail.com',
    'yahoo.con': 'yahoo.com',
    'yahoo.co': 'yahoo.com',

    # Outlook & Hotmail typos
    'hotmial.com': 'hotmail.com',
    'hotmai.com': 'hotmail.com',
    'hotmali.com': 'hotmail.com',
    'hotmal.com': 'hotmail.com',
    'hotmail.con': 'hotmail.com',
    'outlok.com': 'outlook.com',
    'outloo.com': 'outlook.com',
    'outllok.com': 'outlook.com',
    'outlook.con': 'outlook.com',

    # iCloud typos
    'iclod.com': 'icloud.com',
    'icoud.com': 'icloud.com',
    'icloud.con': 'icloud.com',

    # Rediffmail typos
    'redifmail.com': 'rediffmail.com',
    'rediff.com': 'rediffmail.com',
}

# Known major email domains that are 100% valid and always have active MX servers
TRUSTED_MAJOR_DOMAINS = {
    'gmail.com', 'yahoo.com', 'yahoo.in', 'yahoo.co.in', 'ymail.com',
    'outlook.com', 'hotmail.com', 'live.com', 'msn.com',
    'icloud.com', 'me.com', 'mac.com',
    'rediffmail.com', 'protonmail.com', 'proton.me',
    'zoho.com', 'zoho.in', 'aol.com',
    'abcdcampus.in'
}


def check_domain_mx_records(domain: str, timeout: float = 2.5) -> bool:
    """
    Verifies if a domain has active MX (Mail Exchange) DNS records capable of receiving emails.
    Uses Cloudflare and Google DNS-over-HTTPS (DoH) over standard HTTPS Port 443 (bypasses any ISP/firewall blocks).
    Falls back to socket IP resolution.
    Results are cached in Django's cache for 24 hours.
    """
    domain = (domain or '').strip().lower()
    if not domain or '.' not in domain:
        return False

    # Fast path for known major providers
    if domain in TRUSTED_MAJOR_DOMAINS:
        return True

    cache_key = f"mx_valid_{domain}"
    cached_status = cache.get(cache_key)
    if cached_status is not None:
        return bool(cached_status)

    # 1. Try Cloudflare DNS-over-HTTPS (DoH)
    try:
        url = f"https://cloudflare-dns.com/dns-query?name={domain}&type=MX"
        headers = {"accept": "application/dns-json"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            answers = data.get("Answer", [])
            has_mx = any(a.get("type") == 15 for a in answers)
            if has_mx:
                cache.set(cache_key, True, timeout=86400)
                return True
            # Check Status: 3 means NXDOMAIN (domain does not exist at all)
            if data.get("Status") == 3:
                cache.set(cache_key, False, timeout=86400)
                return False
    except Exception as cf_err:
        logger.debug(f"[EmailValidator] Cloudflare DoH check failed for {domain}: {cf_err}")

    # 2. Try Google DNS-over-HTTPS (DoH) fallback
    try:
        url = f"https://dns.google/resolve?name={domain}&type=MX"
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            answers = data.get("Answer", [])
            has_mx = any(a.get("type") == 15 for a in answers)
            if has_mx:
                cache.set(cache_key, True, timeout=86400)
                return True
            if data.get("Status") == 3:
                cache.set(cache_key, False, timeout=86400)
                return False
    except Exception as g_err:
        logger.debug(f"[EmailValidator] Google DoH check failed for {domain}: {g_err}")

    # 3. Fallback: Check if domain resolves to any IPv4 address
    try:
        addr = socket.getaddrinfo(domain, 80, socket.AF_INET)
        if addr:
            # Domain exists and has an IP; give benefit of doubt to avoid false negatives on obscure networks
            cache.set(cache_key, True, timeout=86400)
            return True
    except Exception:
        pass

    # Domain does not resolve anywhere
    cache.set(cache_key, False, timeout=86400)
    return False


def validate_email_deliverability(email: str, check_dns: bool = True) -> tuple[bool, str | None, str | None]:
    """
    Validates email format, detects domain typos, and verifies DNS deliverability.
    
    Returns:
        tuple (is_valid: bool, error_message: str | None, suggested_email: str | None)
    """
    if not email or not isinstance(email, str):
        return False, "Please enter an email address.", None

    clean_email = email.strip().lower()

    if len(clean_email) > 254:
        return False, "Email address is too long (maximum 254 characters).", None

    if not EMAIL_REGEX.match(clean_email):
        return False, "Please enter a valid email format (e.g. name@example.com).", None

    # Check for invalid consecutive dots or symbols
    if '..' in clean_email or clean_email.startswith('.') or '@.' in clean_email or '.@' in clean_email:
        return False, "Email address contains invalid formatting or consecutive dots.", None

    try:
        local_part, domain = clean_email.split('@', 1)
    except ValueError:
        return False, "Email address must contain exactly one '@' symbol.", None

    if not local_part or not domain:
        return False, "Email address must have a username and a domain.", None

    # Check common domain typos
    if domain in DOMAIN_TYPO_MAP:
        corrected_domain = DOMAIN_TYPO_MAP[domain]
        suggested_email = f"{local_part}@{corrected_domain}"
        return (
            False,
            f"Did you mean '{suggested_email}'? Please check your email spelling.",
            suggested_email
        )

    # Check DNS MX record if requested
    if check_dns:
        has_mx = check_domain_mx_records(domain)
        if not has_mx:
            return (
                False,
                f"The email domain '@{domain}' does not appear to exist or cannot receive emails. Please check for typos.",
                None
            )

    return True, None, None
