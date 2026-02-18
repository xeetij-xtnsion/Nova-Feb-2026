"""Mock patient profiles for returning-patient verification (MVP).

Will be replaced by Jane App / ClinicSync Pro integration.
"""

import re
from typing import Optional, Dict

MOCK_PATIENTS = [
    {
        "name": "Sarah Thompson",
        "phone": "(587) 555-0142",
        "preferred_practitioner": "Lorena Bulcao",
        "last_visit": "Jan 15 — 60-min Massage",
        "upcoming_appointment": "Feb 24 — Acupuncture",
        "total_visits": 8,
    },
    {
        "name": "James Mitchell",
        "phone": "(403) 555-0198",
        "preferred_practitioner": "Dr. Ali Nurani",
        "last_visit": "Feb 3 — Naturopathic Follow-Up",
        "upcoming_appointment": None,
        "total_visits": 12,
    },
    {
        "name": "Priya Patel",
        "phone": "(587) 555-0267",
        "preferred_practitioner": "Dr. Chad Patterson",
        "last_visit": "Jan 28 — IV Nutrient Therapy",
        "upcoming_appointment": "Feb 20 — IV Drip",
        "total_visits": 5,
    },
]


def _normalize_phone(raw: str) -> str:
    """Strip non-digit characters so we can compare phone numbers."""
    return re.sub(r"\D", "", raw)


def lookup_patient_by_phone(raw: str) -> Optional[Dict]:
    """Look up a patient by phone number. Returns the patient dict or None."""
    normalized = _normalize_phone(raw)
    for patient in MOCK_PATIENTS:
        if _normalize_phone(patient["phone"]) == normalized:
            return patient
    return None


def is_valid_phone_input(raw: str) -> bool:
    """Return True if the input contains at least 10 digits (plausible phone number)."""
    return len(_normalize_phone(raw)) >= 10
