import json
import os
from datetime import datetime, date
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone
from users.models import Payment, FeeTransaction, TeacherHiddenFeeTransaction, FeeTransactionAudit


def _serialize_val(val):
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    return str(val) if val is not None else None


class Command(BaseCommand):
    help = "Exports all fee transactions, payments, teacher hides, and audit logs to a timestamped JSON backup file."

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default=os.path.join(settings.BASE_DIR, 'backups'),
            help='Directory path where backup JSON will be stored (default: <BASE_DIR>/backups)'
        )
        parser.add_argument(
            '--stdout',
            action='store_true',
            help='Output backup JSON directly to stdout instead of writing to a file'
        )

    def handle(self, *args, **options):
        output_dir = options['output_dir']
        use_stdout = options['stdout']

        now = timezone.now()
        timestamp_str = now.strftime('%Y%m%d_%H%M%S')

        # 1. Collect Payments
        payments_data = []
        for p in Payment.objects.all().order_by('id'):
            payments_data.append({
                'id': p.id,
                'student_id': p.student_id,
                'month': p.month,
                'year': p.year,
                'amount': float(p.amount) if p.amount is not None else 0.0,
                'date_paid': _serialize_val(p.date_paid),
                'created_at': _serialize_val(p.created_at),
                'fee_transaction_id': getattr(p, 'fee_transaction_id', None),
            })

        # 2. Collect FeeTransactions
        transactions_data = []
        for tx in FeeTransaction.objects.all().order_by('id'):
            transactions_data.append({
                'id': tx.id,
                'receipt_number': tx.receipt_number,
                'student_id': tx.student_id,
                'teacher_id': tx.teacher_id,
                'payment_date': _serialize_val(tx.payment_date),
                'expiry_date': _serialize_val(tx.expiry_date),
                'service_snapshot': tx.service_snapshot,
                'months_snapshot': tx.months_snapshot,
                'total_amount': float(tx.total_amount) if tx.total_amount is not None else 0.0,
                'email_sent': tx.email_sent,
                'whatsapp_sent': tx.whatsapp_sent,
                'is_hidden_by_student': tx.is_hidden_by_student,
                'deleted_at': _serialize_val(tx.deleted_at),
                'deleted_by_id': tx.deleted_by_id,
                'student_name_snapshot': tx.student_name_snapshot,
                'roll_number_snapshot': tx.roll_number_snapshot,
                'mobile_snapshot': tx.mobile_snapshot,
                'course_snapshot': tx.course_snapshot,
                'created_at': _serialize_val(tx.created_at),
                'last_modified_at': _serialize_val(getattr(tx, 'last_modified_at', None)),
                'last_modified_by_id': getattr(tx, 'last_modified_by_id', None),
                'revision_count': getattr(tx, 'revision_count', 0),
            })

        # 3. Collect TeacherHiddenFeeTransactions
        teacher_hides_data = []
        for th in TeacherHiddenFeeTransaction.objects.all().order_by('id'):
            teacher_hides_data.append({
                'id': th.id,
                'teacher_id': th.teacher_id,
                'transaction_id': th.transaction_id,
                'hidden_at': _serialize_val(th.hidden_at),
            })

        # 4. Collect FeeTransactionAudits
        audits_data = []
        for a in FeeTransactionAudit.objects.all().order_by('id'):
            audits_data.append({
                'id': a.id,
                'transaction_id': a.transaction_id,
                'receipt_number': a.receipt_number,
                'student_id': a.student_id,
                'student_name': a.student_name,
                'roll_number': a.roll_number,
                'amount': float(a.amount) if a.amount is not None else None,
                'months': a.months,
                'action': a.action,
                'actor_id': a.actor_id,
                'timestamp': _serialize_val(a.timestamp),
                'reason': a.reason,
            })

        backup_payload = {
            'backup_timestamp': now.isoformat(),
            'counts': {
                'payments': len(payments_data),
                'fee_transactions': len(transactions_data),
                'teacher_hidden_fee_transactions': len(teacher_hides_data),
                'fee_transaction_audits': len(audits_data),
            },
            'payments': payments_data,
            'fee_transactions': transactions_data,
            'teacher_hidden_fee_transactions': teacher_hides_data,
            'fee_transaction_audits': audits_data,
        }

        json_output = json.dumps(backup_payload, indent=2)

        if use_stdout:
            self.stdout.write(json_output)
            return

        os.makedirs(output_dir, exist_ok=True)
        file_name = f"fee_backup_{timestamp_str}.json"
        file_path = os.path.join(output_dir, file_name)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(json_output)

        self.stdout.write(self.style.SUCCESS(
            f"Successfully created fee backup at: {file_path}\n"
            f"Counts: {len(payments_data)} Payments, {len(transactions_data)} FeeTransactions, "
            f"{len(teacher_hides_data)} TeacherHides, {len(audits_data)} Audits."
        ))
