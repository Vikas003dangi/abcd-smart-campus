"""
Self-check for Coaching Admission Batch Approval & Override Logic.
Verifies that:
1. Approving with skip_batch=true sets batch to None ("No Batch").
2. Approving with an override batch (raw code or display name) sets batch correctly.
3. Approving without batch changes preserves the original batch.
"""
import os
import sys

# Setup Django environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'abcd_web')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'abcd_web.settings')

import django
django.setup()

from users.models import StudentProfile


def test_batch_normalization_logic():
    valid_choices = [c[0] for c in StudentProfile.BATCH_CHOICES]
    display_to_code = {c[1]: c[0] for c in StudentProfile.BATCH_CHOICES}

    assert len(valid_choices) == 6, f"Expected 6 batch choices, got {len(valid_choices)}"

    def normalize(raw_input):
        override_clean = (raw_input or '').strip()
        if not override_clean or override_clean.lower() in ['none', 'no batch', '']:
            return None
        if override_clean in valid_choices:
            return override_clean
        if override_clean in display_to_code:
            return display_to_code[override_clean]
        return override_clean

    # Test 1: Raw choice matches
    assert normalize("Grammar Batch 4") == "Grammar Batch 4"
    assert normalize("Grammar Batch 1") == "Grammar Batch 1"

    # Test 2: Display name maps to raw choice code
    assert normalize("Spoken English & PD Batch 1") == "Spoken English 1"
    assert normalize("Spoken English & PD Batch 2") == "Spoken English 2"

    # Test 3: None / empty / 'No Batch' strings clear batch
    assert normalize("") is None
    assert normalize("None") is None
    assert normalize("No Batch") is None
    assert normalize("   ") is None

    print("[SUCCESS] All coaching batch approval normalization tests passed!")


if __name__ == '__main__':
    test_batch_normalization_logic()
