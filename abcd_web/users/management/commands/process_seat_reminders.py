import logging
import time
from django.core.management.base import BaseCommand
from users.utils import process_seat_availability_reminders, process_expired_holds

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Daily maintenance: Process seat reminders and expire holds with standardized logging."

    def handle(self, *args, **options):
        start_time = time.time()
        logger.info("COMMAND START: process_seat_reminders started.")

        stats = {"holds_success": False, "reminders_success": False}

        # 1. Process Expired Holds
        logger.info("MAINTENANCE: Checking for expired holds...")
        try:
            process_expired_holds()
            stats["holds_success"] = True
            logger.info("SUCCESS: Expired holds processed.")
        except Exception as e:
            logger.error("FAILURE: Error in expired holds processing.", exc_info=True)

        # 2. Process Waiting List Reminders
        logger.info("MAINTENANCE: Checking for 'Notify Me' availability...")
        try:
            process_seat_availability_reminders()
            stats["reminders_success"] = True
            logger.info("SUCCESS: Seat availability reminders processed.")
        except Exception as e:
            logger.error("FAILURE: Error in seat availability reminders processing.", exc_info=True)

        duration = time.time() - start_time
        logger.info(
            f"COMMAND END: process_seat_reminders completed in {duration:.2f}s. "
            f"Holds: {'OK' if stats['holds_success'] else 'FAILED'}, "
            f"Reminders: {'OK' if stats['reminders_success'] else 'FAILED'}"
        )