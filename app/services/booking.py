import json
import logging
from datetime import datetime, timedelta, date, time
from typing import Optional, Tuple, List, Dict
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    settings,
    practitioner_services,
    get_practitioners_for_service,
    get_delivery_modes,
    filter_practitioners_by_delivery_mode,
)
from app.models.appointment import Appointment, AppointmentStatus
from app.services.nlp_utils import word_match

logger = logging.getLogger(__name__)

# Booking states
STATES = [
    "idle",
    "select_service",
    "select_delivery_mode",
    "select_practitioner",
    "select_date",
    "select_time",
    "collect_name",
    "collect_phone",
    "confirm",
    "booked",
]

BOOKING_TRIGGERS = [
    "book", "schedule", "reserve", "booking",
    "sign up", "sign me up", "make an appointment",
]

# If any of these appear alongside a booking trigger, it's an info request, not a booking
BOOKING_EXCLUDE_PHRASES = [
    # Info requests
    "upcoming", "my visit", "my upcoming", "details of", "tell me about",
    "what about", "when is", "what are the details",
    "reschedule", "rescheduling", "resched", "cancel my", "cancellation",
    "change my appointment", "move my appointment",
    "existing", "current", "status",
    # Uncertainty
    "not sure", "don't know", "dont know", "unsure", "no idea",
    # Negation / refusal
    "don't want", "dont want", "do not want",
    "don't need", "dont need", "do not need",
    "not looking to", "not ready", "no thanks", "not interested",
    "don't book", "dont book", "not book", "no book",
]

CONFUSION_PHRASES = [
    "don't know", "dont know", "not sure", "unsure", "confused",
    "help me", "recommend", "what should", "no idea", "which one",
    "i'm not sure", "im not sure", "i'm not certain", "im not certain",
    "suggest", "idk", "hmm", "what do you",
    "what are my options", "who are", "tell me more",
]

# ── Consultation sub-options (shown when user wants an initial consultation) ──

CONSULTATION_OPTIONS = [
    {
        "label": "Initial Naturopathic Consultation",
        "detail": "~80 min · $295",
        "maps_to_service": "Naturopathic Medicine",
    },
    {
        "label": "Initial Injection/IV Consultation",
        "detail": "~80 min · from $290",
        "maps_to_service": "Naturopathic Medicine",
    },
    {
        "label": "Meet & Greet",
        "detail": "Free · 15 min",
        "maps_to_service": "Naturopathic Medicine",
    },
]

# Maps keywords in the booking message to a direct service selection
SERVICE_KEYWORDS = {
    "massage": "Massage Therapy",
    "acupuncture": "Acupuncture",
}

CONSULT_KEYWORDS = [
    "initial consultation", "consultation", "meet and greet", "meet & greet",
    "book a meeting", "schedule a meeting", "meet with a doctor",
    "meet with a naturopath", "meet with dr",
]


class BookingService:
    """Redis-backed booking state machine."""

    def __init__(self, redis_client: Optional[redis.Redis]):
        self.redis = redis_client
        self.ttl = settings.booking_state_ttl
        self.services = settings.clinic_services

    def _key(self, session_id: str) -> str:
        return f"session:{session_id}:booking"

    # ── state helpers ──────────────────────────────────────────────

    async def _get_state(self, session_id: str) -> Dict:
        if not self.redis:
            return {"state": "idle"}
        try:
            raw = await self.redis.get(self._key(session_id))
            return json.loads(raw) if raw else {"state": "idle"}
        except Exception:
            return {"state": "idle"}

    async def _set_state(self, session_id: str, data: Dict) -> None:
        if not self.redis:
            return
        try:
            await self.redis.set(self._key(session_id), json.dumps(data), ex=self.ttl)
        except Exception as e:
            logger.warning(f"Failed to save booking state: {e}")

    async def _clear_state(self, session_id: str) -> None:
        if not self.redis:
            return
        try:
            await self.redis.delete(self._key(session_id))
        except Exception:
            pass

    async def is_active(self, session_id: str) -> bool:
        """True if a booking flow is in progress."""
        state = await self._get_state(session_id)
        return state.get("state", "idle") not in ("idle", "booked")

    # ── replay current step ──────────────────────────────────────────

    async def _replay_step(self, session_id: str, data: Dict) -> Tuple[str, List[Dict]]:
        """Re-show the current step's prompt and buttons."""
        state = data.get("state", "idle")

        if state == "select_service":
            if data.get("show_consultation"):
                actions = []
                for opt in CONSULTATION_OPTIONS:
                    actions.append({
                        "label": f"{opt['label']} — {opt['detail']}",
                        "value": opt["label"],
                        "action_type": "booking",
                    })
                actions.append({"label": "Not sure", "value": "Not sure", "action_type": "booking"})
                actions.append({"label": "Back to Services", "value": "back to services", "action_type": "quick_reply"})
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "select_consultation_type", actions
            actions = [{"label": s, "value": s, "action_type": "booking"} for s in self.services]
            actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
            return "select_service", actions

        if state == "select_delivery_mode":
            modes = get_delivery_modes(data.get("service_display"), data.get("service", ""))
            actions = [{"label": m, "value": m, "action_type": "booking"} for m in modes]
            actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
            return "select_delivery_mode", actions

        if state == "select_practitioner":
            service = data.get("service", "")
            practitioners = get_practitioners_for_service(service)
            if data.get("delivery_mode"):
                practitioners = filter_practitioners_by_delivery_mode(practitioners, data["delivery_mode"])
            preferred = data.get("preferred_practitioner", "")
            step_hint = "select_practitioner"
            if preferred:
                pref_list = [p for p in practitioners if p["name"] == preferred]
                rest_list = [p for p in practitioners if p["name"] != preferred]
                if pref_list:
                    practitioners = pref_list + rest_list
                    step_hint = "select_practitioner_with_preferred"
            actions = [
                {"label": f"{p['name']} ({p['title']})", "value": p["name"], "action_type": "booking"}
                for p in practitioners
            ]
            actions.append({"label": "No preference", "value": "No preference", "action_type": "booking"})
            actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
            return step_hint, actions

        if state == "select_date":
            dates = self._available_dates()
            actions = [
                {"label": self._format_date(d), "value": d, "action_type": "booking"} for d in dates
            ]
            actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
            return "select_date", actions

        if state == "select_time":
            times = self._available_times()
            actions = [
                {"label": t, "value": t, "action_type": "booking"} for t in times
            ]
            actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
            return "select_time", actions

        if state == "collect_name":
            return "collect_name", [
                {"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"}
            ]

        if state == "collect_phone":
            return "collect_phone", [
                {"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"}
            ]

        if state == "confirm":
            return "confirm", [
                {"label": "Confirm Booking", "value": "confirm", "action_type": "booking"},
                {"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"},
            ]

        return "idle", []

    # ── intent detection ───────────────────────────────────────────

    # Confusion phrases that override a booking trigger.
    # "help me" is excluded because "help me book" IS a valid booking intent.
    _BOOKING_CONFUSION_EXCLUDES = [
        p for p in CONFUSION_PHRASES if p not in ("help me",)
    ]

    @staticmethod
    def is_booking_intent(message: str) -> bool:
        msg = message.lower()
        if any(phrase in msg for phrase in BOOKING_EXCLUDE_PHRASES):
            return False
        if any(phrase in msg for phrase in BookingService._BOOKING_CONFUSION_EXCLUDES):
            return False
        # Use word-boundary matching to avoid "book" matching inside "facebook"
        return any(word_match(trigger, msg) for trigger in BOOKING_TRIGGERS)

    # ── date/time helpers ──────────────────────────────────────────

    @staticmethod
    def _ordinal(n: int) -> str:
        """Return day number with ordinal suffix: 1st, 2nd, 3rd, etc."""
        if 11 <= n <= 13:
            return f"{n}th"
        return f"{n}{['th','st','nd','rd','th','th','th','th','th','th'][n % 10]}"

    @staticmethod
    def _format_date(iso: str) -> str:
        """Convert '2026-02-16' to '16th Feb, 2026'."""
        d = datetime.strptime(iso, "%Y-%m-%d").date()
        return f"{BookingService._ordinal(d.day)} {d.strftime('%b')}, {d.year}"

    @staticmethod
    def _available_dates(offset: int = 0) -> List[str]:
        """Return 5 weekdays starting from tomorrow, skipping *offset* weekdays."""
        dates = []
        d = date.today() + timedelta(days=1)
        skipped = 0
        while len(dates) < 5:
            if d.weekday() < 5:  # Mon-Fri
                if skipped < offset:
                    skipped += 1
                else:
                    dates.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=1)
        return dates

    @staticmethod
    def _match_natural_date(msg: str, available_dates: List[str]) -> Optional[str]:
        """Match natural language date input against available ISO dates.

        Handles: "2nd March is fine", "march 2", "the 2nd", "monday", "tuesday", etc.
        Returns the matching ISO date string, or None.
        """
        import re as _re

        _MONTHS = {
            "jan": 1, "january": 1, "feb": 2, "february": 2,
            "mar": 3, "march": 3, "apr": 4, "april": 4,
            "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
            "aug": 8, "august": 8, "sep": 9, "september": 9,
            "oct": 10, "october": 10, "nov": 11, "november": 11,
            "dec": 12, "december": 12,
        }
        _WEEKDAYS = {
            "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1,
            "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3, "thurs": 3,
            "friday": 4, "fri": 4, "saturday": 5, "sat": 5,
            "sunday": 6, "sun": 6,
        }

        # Parse available dates into date objects
        parsed = []
        for iso in available_dates:
            try:
                parsed.append((iso, datetime.strptime(iso, "%Y-%m-%d").date()))
            except ValueError:
                continue

        if not parsed:
            return None

        # Extract day number from ordinals like "2nd", "3rd", "15th" or plain "2", "15"
        day_match = _re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?\b', msg)
        day_num = int(day_match.group(1)) if day_match else None

        # Extract month
        month_num = None
        for name, num in _MONTHS.items():
            if name in msg:
                month_num = num
                break

        # Extract weekday
        weekday_num = None
        for name, num in _WEEKDAYS.items():
            if name in msg:
                weekday_num = num
                break

        # Match by day + month (most specific)
        if day_num and month_num:
            for iso, d in parsed:
                if d.day == day_num and d.month == month_num:
                    return iso

        # Match by day number only (within available dates)
        if day_num:
            matches = [(iso, d) for iso, d in parsed if d.day == day_num]
            if len(matches) == 1:
                return matches[0][0]

        # Match by weekday name
        if weekday_num is not None:
            matches = [(iso, d) for iso, d in parsed if d.weekday() == weekday_num]
            if len(matches) == 1:
                return matches[0][0]

        # Match by label format (e.g. "2nd Mar, 2026" typed directly)
        for iso, d in parsed:
            label = BookingService._format_date(iso).lower()
            if label in msg:
                return iso

        return None

    @staticmethod
    def _available_times() -> List[str]:
        """Return hourly slots between booking_hours_start and booking_hours_end."""
        slots = []
        for h in range(settings.booking_hours_start, settings.booking_hours_end):
            slots.append(f"{h:02d}:00")
        return slots

    @staticmethod
    def _match_natural_time(msg: str, valid_times: List[str]) -> Optional[str]:
        """Match natural language time input against available time slots.

        Handles: "16", "4 pm", "4pm", "4:00 pm", "4:00", "four", "at 2", etc.
        Returns the matching HH:00 string, or None.
        """
        import re as _re

        _WORD_NUMS = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12, "noon": 12,
        }

        hour = None

        # Try "4:00 pm", "4:30pm", "16:00" etc.
        m = _re.search(r'(\d{1,2})\s*:\s*\d{2}\s*(am|pm|a\.m|p\.m)?', msg)
        if m:
            hour = int(m.group(1))
            if m.group(2) and m.group(2).startswith('p') and hour < 12:
                hour += 12
            elif m.group(2) and m.group(2).startswith('a') and hour == 12:
                hour = 0

        # Try "4 pm", "4pm", "16"
        if hour is None:
            m = _re.search(r'\b(\d{1,2})\s*(am|pm|a\.m|p\.m)?\b', msg)
            if m:
                hour = int(m.group(1))
                if m.group(2) and m.group(2).startswith('p') and hour < 12:
                    hour += 12
                elif m.group(2) and m.group(2).startswith('a') and hour == 12:
                    hour = 0
                elif not m.group(2) and hour < 8:
                    # Bare number < 8 likely means PM (no one books at 1am)
                    hour += 12

        # Try word numbers: "four", "noon", etc.
        if hour is None:
            for word, num in _WORD_NUMS.items():
                if word in msg:
                    hour = num
                    if "pm" in msg or "p.m" in msg:
                        if hour < 12:
                            hour += 12
                    elif hour < 8:
                        hour += 12
                    break

        if hour is not None:
            slot = f"{hour:02d}:00"
            if slot in valid_times:
                return slot

        return None

    @staticmethod
    def _parse_time_preference(message: str, valid_times: List[str]) -> List[str]:
        """Interpret natural language time preferences and return matching slots.

        Returns a filtered subset of valid_times, or empty list if no preference detected.
        """
        msg = message.strip().lower()

        # Map phrases to hour ranges (inclusive start, exclusive end)
        # "phrases" = multi-word, safe for substring; "words" = need word-boundary
        _TIME_PHRASES = [
            # After work / evening / later
            (["after work", "after 5", "after five", "evening", "late afternoon",
              "later in the day", "end of day", "last slot",
              "anything later", "something later", "any later"], ["later"], 15, 24),
            # Afternoon
            (["afternoon", "after lunch", "after noon", "midday"], ["pm"], 12, 24),
            # Morning / early
            (["morning", "early", "first thing", "before lunch", "before noon"], ["am"], 0, 12),
            # Lunch / midday
            (["lunch", "noon", "around 12", "around noon"], [], 11, 14),
        ]

        for phrases, words, start_h, end_h in _TIME_PHRASES:
            if any(phrase in msg for phrase in phrases) or any(word_match(w, msg) for w in words):
                filtered = [t for t in valid_times if start_h <= int(t.split(":")[0]) < end_h]
                if filtered:
                    return filtered

        return []

    # ── main entry point ───────────────────────────────────────────

    async def start(
        self,
        session_id: str,
        verified_patient: Optional[Dict] = None,
        message: str = "",
        inferred_service: Optional[str] = None,
        inferred_consultation: bool = False,
    ) -> Tuple[str, List[Dict]]:
        """Start the booking flow. Returns (step_hint, actions).

        If *verified_patient* is provided, pre-fill name, phone, and
        preferred_practitioner so those collection steps are skipped.

        *message* is the user's raw text — used to detect service intent
        so we can skip to relevant options instead of showing the full list.
        """
        initial: Dict = {"state": "select_service"}
        if verified_patient:
            initial["name"] = verified_patient.get("name", "")
            initial["phone"] = verified_patient.get("phone", "")
            initial["preferred_practitioner"] = verified_patient.get(
                "preferred_practitioner", ""
            )

        msg = message.lower()

        # Detect practitioner name from message (e.g. "book with Dr. Ali Nurani")
        detected_prac = None
        for prac_name in practitioner_services:
            if prac_name.lower() in msg:
                detected_prac = prac_name
                break
        if not detected_prac:
            for prac_name in practitioner_services:
                last_name = prac_name.split()[-1]
                if word_match(last_name, msg):
                    detected_prac = prac_name
                    break
        if detected_prac:
            initial["preferred_practitioner"] = detected_prac
            initial["practitioner"] = detected_prac

        # Helper: auto-select a specific consultation option and advance
        async def _select_consultation(opt):
            initial["service"] = opt["maps_to_service"]
            initial["service_display"] = opt["label"]
            modes = get_delivery_modes(opt["label"], opt["maps_to_service"])
            if len(modes) == 1:
                initial["delivery_mode"] = modes[0]
            else:
                initial["state"] = "select_delivery_mode"
                await self._set_state(session_id, initial)
                actions = [{"label": m, "value": m, "action_type": "booking"} for m in modes]
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "select_delivery_mode", actions

            practitioners = get_practitioners_for_service(opt["maps_to_service"])
            practitioners = filter_practitioners_by_delivery_mode(practitioners, initial["delivery_mode"])

            if not practitioners or initial.get("practitioner"):
                if not practitioners and not initial.get("practitioner"):
                    initial["practitioner"] = None
                initial["state"] = "select_date"
                await self._set_state(session_id, initial)
                dates = self._available_dates()
                actions = [
                    {"label": self._format_date(d), "value": d, "action_type": "booking"} for d in dates
                ]
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "select_date", actions

            initial["state"] = "select_practitioner"
            await self._set_state(session_id, initial)
            preferred = initial.get("preferred_practitioner", "")
            step_hint = "select_practitioner"
            if preferred:
                pref_list = [p for p in practitioners if p["name"] == preferred]
                rest_list = [p for p in practitioners if p["name"] != preferred]
                if pref_list:
                    practitioners = pref_list + rest_list
                    step_hint = "select_practitioner_with_preferred"
            actions = [
                {"label": f"{p['name']} ({p['title']})", "value": p["name"], "action_type": "booking"}
                for p in practitioners
            ]
            actions.append({"label": "No preference", "value": "No preference", "action_type": "booking"})
            actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
            return step_hint, actions

        # Helper: show consultation sub-options
        async def _show_consultation():
            initial["show_consultation"] = True
            await self._set_state(session_id, initial)
            actions = []
            for opt in CONSULTATION_OPTIONS:
                actions.append({
                    "label": f"{opt['label']} — {opt['detail']}",
                    "value": opt["label"],
                    "action_type": "booking",
                })
            actions.append({"label": "Not sure", "value": "Not sure", "action_type": "booking"})
            actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
            return "select_consultation_type", actions

        # Helper: auto-select a service and advance to practitioner/date
        async def _select_service(service):
            initial["service"] = service
            initial["delivery_mode"] = "In-person"  # massage/acupuncture are in-person only
            practitioners = get_practitioners_for_service(service)
            if not practitioners:
                initial["state"] = "select_date"
                initial["practitioner"] = None
                await self._set_state(session_id, initial)
                dates = self._available_dates()
                actions = [
                    {"label": self._format_date(d), "value": d, "action_type": "booking"}
                    for d in dates
                ]
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "select_date", actions

            # Skip practitioner step if already selected (e.g. "book with Dr. X")
            if initial.get("practitioner"):
                initial["state"] = "select_date"
                await self._set_state(session_id, initial)
                dates = self._available_dates()
                actions = [
                    {"label": self._format_date(d), "value": d, "action_type": "booking"}
                    for d in dates
                ]
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "select_date", actions

            initial["state"] = "select_practitioner"
            await self._set_state(session_id, initial)

            preferred = initial.get("preferred_practitioner", "")
            step_hint = "select_practitioner"
            if preferred:
                pref_list = [p for p in practitioners if p["name"] == preferred]
                rest_list = [p for p in practitioners if p["name"] != preferred]
                if pref_list:
                    practitioners = pref_list + rest_list
                    step_hint = "select_practitioner_with_preferred"

            actions = [
                {"label": f"{p['name']} ({p['title']})", "value": p["name"], "action_type": "booking"}
                for p in practitioners
            ]
            actions.append({"label": "No preference", "value": "No preference", "action_type": "booking"})
            actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
            return step_hint, actions

        # ── Priority 1: Explicit keywords in the user's message ──

        # 1a. Specific consultation type → auto-select and advance
        _SPECIFIC_CONSULT = [
            (["meet and greet", "meet & greet", "meet&greet"], "Meet & Greet"),
            (["initial naturopathic"], "Initial Naturopathic Consultation"),
            (["initial injection", "initial iv", "iv consultation"], "Initial Injection/IV Consultation"),
        ]
        for phrases, label in _SPECIFIC_CONSULT:
            if any(p in msg for p in phrases):
                opt = next(o for o in CONSULTATION_OPTIONS if o["label"] == label)
                return await _select_consultation(opt)

        # 1b. Generic consultation keywords → show sub-options
        if any(kw in msg for kw in CONSULT_KEYWORDS):
            return await _show_consultation()

        # 1c. Service keywords in message
        for keyword, service in SERVICE_KEYWORDS.items():
            if word_match(keyword, msg):
                return await _select_service(service)

        # ── Priority 2: Preferred practitioner → filter to their services ──
        if detected_prac and detected_prac in practitioner_services:
            prac_info = practitioner_services[detected_prac]
            prac_svc = [s for s in self.services if s in prac_info["services"]]
            if len(prac_svc) == 1:
                # Only one bookable service → auto-select, skip practitioner step
                svc = prac_svc[0]
                initial["service"] = svc
                modes = get_delivery_modes(None, svc)
                if len(modes) == 1:
                    initial["delivery_mode"] = modes[0]
                    initial["state"] = "select_date"
                    await self._set_state(session_id, initial)
                    dates = self._available_dates()
                    actions = [
                        {"label": self._format_date(d), "value": d, "action_type": "booking"}
                        for d in dates
                    ]
                    actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                    return "select_date", actions
                else:
                    initial["state"] = "select_delivery_mode"
                    await self._set_state(session_id, initial)
                    actions = [{"label": m, "value": m, "action_type": "booking"} for m in modes]
                    actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                    return "select_delivery_mode", actions
            elif prac_svc:
                # Multiple services → show filtered list
                await self._set_state(session_id, initial)
                actions = [{"label": s, "value": s, "action_type": "booking"} for s in prac_svc]
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "select_service", actions

        # ── Priority 3: Inferred from conversation context ──
        # (only when the message itself doesn't specify)

        # 3a. Inferred consultation from history
        if inferred_consultation:
            return await _show_consultation()

        # 3b. Inferred service from history
        if inferred_service and inferred_service in self.services:
            return await _select_service(inferred_service)

        # ── Generic → show full service list ──
        await self._set_state(session_id, initial)
        actions = [{"label": s, "value": s, "action_type": "booking"} for s in self.services]
        actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
        return "select_service", actions

    async def process_step(
        self, session_id: str, message: str, db: AsyncSession
    ) -> Tuple[str, List[Dict]]:
        """
        Advance the state machine one step.
        Returns (step_hint, actions) where step_hint tells the LLM
        what just happened and what to ask next.
        """
        data = await self._get_state(session_id)
        state = data.get("state", "idle")

        # Cancel from any step
        _CANCEL_PHRASES = ("cancel", "cancel booking", "cancel it", "cancel my booking",
                           "i want to cancel", "please cancel", "stop booking", "nevermind",
                           "never mind", "forget it")
        if message.strip().lower() in _CANCEL_PHRASES:
            await self._clear_state(session_id)
            return "cancelled", []

        # "Continue" — re-show current step options
        if message.strip().lower() == "continue":
            return await self._replay_step(session_id, data)

        # ── Mid-flow intent change detection ───────────────────
        msg_lower = message.strip().lower()

        # Don't restart for exact button clicks (e.g. "Meet & Greet", "Acupuncture")
        exact_buttons = {s.lower() for s in self.services}
        exact_buttons.update(opt["label"].lower() for opt in CONSULTATION_OPTIONS)
        exact_buttons.update({"not sure", "no preference"})

        if msg_lower not in exact_buttons and state not in ("idle", "booked"):
            # ── Rescheduling / cancellation question (break out of booking) ──
            _RESCHED_PHRASES = (
                "reschedule", "rescheduling", "reschedul",
                "cancel my", "cancellation policy", "cancel an appointment",
                "change my appointment", "move my appointment",
                "how late can i cancel", "no show", "no-show",
                "policy",
            )
            if any(p in msg_lower for p in _RESCHED_PHRASES):
                return "rescheduling_policy", []

            # ── Practitioner change (rewind, not restart) ──
            # Detect at steps after practitioner selection (date, time, etc.)
            if state in ("select_date", "select_time", "collect_name", "collect_phone", "confirm"):
                _PRAC_CHANGE_PHRASES = (
                    "other doctor", "another doctor", "different doctor",
                    "other practitioner", "another practitioner", "different practitioner",
                    "someone else", "somebody else", "change the doctor",
                    "change the practitioner", "change practitioner", "change doctor",
                    "switch doctor", "switch practitioner", "not with",
                    "other therapist", "different therapist", "another therapist",
                )
                wants_prac_change = any(p in msg_lower for p in _PRAC_CHANGE_PHRASES)

                # Also detect a specific practitioner name that differs from current
                if not wants_prac_change:
                    current_prac = (data.get("practitioner") or "").lower()
                    for prac_name in practitioner_services:
                        if prac_name.lower() in msg_lower and prac_name.lower() != current_prac:
                            wants_prac_change = True
                            data["preferred_practitioner"] = prac_name
                            break
                        parts = prac_name.split()
                        first_name = parts[0].lower()
                        last_name = parts[-1].lower()
                        if word_match(first_name, msg_lower) and prac_name.lower() != current_prac:
                            wants_prac_change = True
                            data["preferred_practitioner"] = prac_name
                            break
                        if word_match(last_name, msg_lower) and prac_name.lower() != current_prac:
                            wants_prac_change = True
                            data["preferred_practitioner"] = prac_name
                            break

                if wants_prac_change:
                    # Rewind to practitioner step (keep service, delivery mode)
                    data["state"] = "select_practitioner"
                    data.pop("practitioner", None)
                    data.pop("date", None)
                    data.pop("date_offset", None)
                    data.pop("time", None)
                    await self._set_state(session_id, data)
                    return await self._replay_step(session_id, data)

            restart = False
            # Consultation intent
            if any(kw in msg_lower for kw in CONSULT_KEYWORDS):
                restart = True
            # Different service keyword
            if not restart:
                current_service = data.get("service", "")
                for kw, svc in SERVICE_KEYWORDS.items():
                    if word_match(kw, msg_lower) and svc != current_service:
                        restart = True
                        break
            if restart:
                # Reconstruct verified_patient from stored booking state
                vp = None
                if data.get("name") and data.get("phone"):
                    vp = {
                        "name": data["name"],
                        "phone": data["phone"],
                        "preferred_practitioner": data.get("preferred_practitioner", ""),
                    }
                await self._clear_state(session_id)
                return await self.start(session_id, verified_patient=vp, message=message)

            # ── Exit / reconsider intent (state preserved) ─────
            # Only at steps beyond select_service (which has its own confusion handler)
            if state != "select_service":
                _EXIT_PHRASES = [
                    "idk what", "don't know what", "dont know what",
                    "not sure what", "unsure what",
                    "changed my mind", "change my mind",
                    "never mind", "nevermind", "nvm",
                    "not anymore", "don't want", "dont want", "do not want",
                    "let me think", "think about it",
                    "i don't think", "i dont think",
                    "hold on", "actually no",
                ]
                if any(phrase in msg_lower for phrase in _EXIT_PHRASES):
                    return "booking_confused", [
                        {"label": "Continue Booking", "value": "continue", "action_type": "booking"},
                        {"label": "Our Services", "value": "What services do you offer?", "action_type": "quick_reply"},
                        {"label": "Cancel Booking", "value": "Cancel", "action_type": "quick_reply"},
                    ]

        # ── select_service ─────────────────────────────────────
        if state == "select_service":
            msg_lower = message.strip().lower()

            # "Back to Services" — clear consultation flag, show full service list
            if msg_lower in ("back to services", "back", "show services"):
                data.pop("show_consultation", None)
                await self._set_state(session_id, data)
                actions = [{"label": s, "value": s, "action_type": "booking"} for s in self.services]
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "select_service", actions

            # Detect confusion → show all consultation options (including free Meet & Greet)
            if msg_lower == "not sure" or any(phrase in msg_lower for phrase in CONFUSION_PHRASES):
                data["show_consultation"] = True
                await self._set_state(session_id, data)
                actions = []
                for opt in CONSULTATION_OPTIONS:
                    actions.append({
                        "label": f"{opt['label']} — {opt['detail']}",
                        "value": opt["label"],
                        "action_type": "booking",
                    })
                actions.append({"label": "Back to Services", "value": "back to services", "action_type": "quick_reply"})
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "recommend_consult", actions

            # Check consultation sub-options first
            consultation_map = {
                opt["label"].lower(): opt for opt in CONSULTATION_OPTIONS
            }
            if msg_lower in consultation_map:
                opt = consultation_map[msg_lower]
                data.pop("show_consultation", None)
                data["service"] = opt["maps_to_service"]
                data["service_display"] = opt["label"]

                # ── Delivery mode gate ──
                modes = get_delivery_modes(opt["label"], opt["maps_to_service"])
                if len(modes) == 1:
                    data["delivery_mode"] = modes[0]
                else:
                    data["state"] = "select_delivery_mode"
                    await self._set_state(session_id, data)
                    actions = [{"label": m, "value": m, "action_type": "booking"} for m in modes]
                    actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                    return "select_delivery_mode", actions

                practitioners = get_practitioners_for_service(opt["maps_to_service"])
                practitioners = filter_practitioners_by_delivery_mode(practitioners, data["delivery_mode"])

                if not practitioners:
                    if not data.get("practitioner"):
                        data["practitioner"] = None
                    data["state"] = "select_date"
                    await self._set_state(session_id, data)
                    dates = self._available_dates()
                    actions = [
                        {"label": self._format_date(d), "value": d, "action_type": "booking"} for d in dates
                    ]
                    actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                    return "select_date", actions

                # Skip practitioner step if already selected
                if data.get("practitioner"):
                    data["state"] = "select_date"
                    await self._set_state(session_id, data)
                    dates = self._available_dates()
                    actions = [
                        {"label": self._format_date(d), "value": d, "action_type": "booking"} for d in dates
                    ]
                    actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                    return "select_date", actions

                data["state"] = "select_practitioner"
                await self._set_state(session_id, data)

                preferred = data.get("preferred_practitioner", "")
                step_hint = "select_practitioner"
                if preferred:
                    pref_list = [p for p in practitioners if p["name"] == preferred]
                    rest_list = [p for p in practitioners if p["name"] != preferred]
                    if pref_list:
                        practitioners = pref_list + rest_list
                        step_hint = "select_practitioner_with_preferred"

                actions = [
                    {"label": f"{p['name']} ({p['title']})", "value": p["name"], "action_type": "booking"}
                    for p in practitioners
                ]
                actions.append({"label": "No preference", "value": "No preference", "action_type": "booking"})
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return step_hint, actions

            # Consultation keywords typed at service step → show sub-options
            if any(kw in msg_lower for kw in CONSULT_KEYWORDS):
                data["show_consultation"] = True
                await self._set_state(session_id, data)
                actions = []
                for opt in CONSULTATION_OPTIONS:
                    actions.append({
                        "label": f"{opt['label']} — {opt['detail']}",
                        "value": opt["label"],
                        "action_type": "booking",
                    })
                actions.append({"label": "Not sure", "value": "Not sure", "action_type": "booking"})
                actions.append({"label": "Back to Services", "value": "back to services", "action_type": "quick_reply"})
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "select_consultation_type", actions

            # Validate against regular services
            chosen = None
            for svc in self.services:
                if msg_lower == svc.lower():
                    chosen = svc
                    break
            if not chosen:
                # retry
                actions = [{"label": s, "value": s, "action_type": "booking"} for s in self.services]
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "invalid_service", actions

            data["service"] = chosen
            data.pop("show_consultation", None)

            # ── Delivery mode gate ──
            modes = get_delivery_modes(data.get("service_display"), chosen)
            if len(modes) == 1:
                data["delivery_mode"] = modes[0]
            else:
                data["state"] = "select_delivery_mode"
                await self._set_state(session_id, data)
                actions = [{"label": m, "value": m, "action_type": "booking"} for m in modes]
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "select_delivery_mode", actions

            practitioners = get_practitioners_for_service(chosen)
            practitioners = filter_practitioners_by_delivery_mode(practitioners, data["delivery_mode"])

            # Skip practitioner step if no practitioners offer this service
            if not practitioners:
                if not data.get("practitioner"):
                    data["practitioner"] = None
                data["state"] = "select_date"
                await self._set_state(session_id, data)

                dates = self._available_dates()
                actions = [
                    {"label": self._format_date(d), "value": d, "action_type": "booking"} for d in dates
                ]
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "select_date", actions

            # Skip practitioner step if already selected (e.g. "book with Dr. X")
            if data.get("practitioner"):
                data["state"] = "select_date"
                await self._set_state(session_id, data)
                dates = self._available_dates()
                actions = [
                    {"label": self._format_date(d), "value": d, "action_type": "booking"} for d in dates
                ]
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "select_date", actions

            data["state"] = "select_practitioner"
            await self._set_state(session_id, data)

            # Reorder so preferred practitioner appears first (if applicable)
            preferred = data.get("preferred_practitioner", "")
            step_hint = "select_practitioner"
            if preferred:
                pref_list = [p for p in practitioners if p["name"] == preferred]
                rest_list = [p for p in practitioners if p["name"] != preferred]
                if pref_list:
                    practitioners = pref_list + rest_list
                    step_hint = "select_practitioner_with_preferred"
                    data["preferred_practitioner"] = preferred
                    await self._set_state(session_id, data)

            actions = [
                {"label": f"{p['name']} ({p['title']})", "value": p["name"], "action_type": "booking"}
                for p in practitioners
            ]
            actions.append({"label": "No preference", "value": "No preference", "action_type": "booking"})
            actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
            return step_hint, actions

        # ── select_delivery_mode ───────────────────────────────
        if state == "select_delivery_mode":
            modes = get_delivery_modes(data.get("service_display"), data.get("service", ""))
            valid = [m.lower() for m in modes]
            if message.strip().lower() not in valid:
                actions = [{"label": m, "value": m, "action_type": "booking"} for m in modes]
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "invalid_delivery_mode", actions

            # Store the properly-cased mode
            for m in modes:
                if message.strip().lower() == m.lower():
                    data["delivery_mode"] = m
                    break

            service = data.get("service", "")
            practitioners = get_practitioners_for_service(service)
            practitioners = filter_practitioners_by_delivery_mode(practitioners, data["delivery_mode"])

            if not practitioners:
                if not data.get("practitioner"):
                    data["practitioner"] = None
                data["state"] = "select_date"
                await self._set_state(session_id, data)
                dates = self._available_dates()
                actions = [
                    {"label": self._format_date(d), "value": d, "action_type": "booking"} for d in dates
                ]
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "select_date", actions

            # Skip practitioner step if already selected (e.g. "book with Dr. X")
            if data.get("practitioner"):
                data["state"] = "select_date"
                await self._set_state(session_id, data)
                dates = self._available_dates()
                actions = [
                    {"label": self._format_date(d), "value": d, "action_type": "booking"} for d in dates
                ]
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "select_date", actions

            data["state"] = "select_practitioner"
            await self._set_state(session_id, data)

            preferred = data.get("preferred_practitioner", "")
            step_hint = "select_practitioner"
            if preferred:
                pref_list = [p for p in practitioners if p["name"] == preferred]
                rest_list = [p for p in practitioners if p["name"] != preferred]
                if pref_list:
                    practitioners = pref_list + rest_list
                    step_hint = "select_practitioner_with_preferred"

            actions = [
                {"label": f"{p['name']} ({p['title']})", "value": p["name"], "action_type": "booking"}
                for p in practitioners
            ]
            actions.append({"label": "No preference", "value": "No preference", "action_type": "booking"})
            actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
            return step_hint, actions

        # ── select_practitioner ────────────────────────────────
        if state == "select_practitioner":
            msg_lower = message.strip().lower()
            service = data.get("service", "")
            practitioners = get_practitioners_for_service(service)
            # Filter by delivery mode if set (e.g. Virtual → only virtual practitioners)
            if data.get("delivery_mode"):
                practitioners = filter_practitioners_by_delivery_mode(practitioners, data["delivery_mode"])
            valid_names = [p["name"].lower() for p in practitioners]

            # Acceptance phrases → pick preferred practitioner, or no preference
            # Single-word accepts — match as whole words only
            _SINGLE_ACCEPTS = {"sure", "yep", "yeah", "ok", "okay", "perfect"}
            # Multi-word accepts — safe as substrings
            _MULTI_ACCEPTS = ("i'm good", "im good", "i am good", "sounds good",
                              "that's fine", "thats fine", "works for me",
                              "go ahead", "let's go", "lets go")
            msg_words = set(msg_lower.split())
            if (msg_words & _SINGLE_ACCEPTS) or any(p in msg_lower for p in _MULTI_ACCEPTS):
                preferred = data.get("preferred_practitioner", "")
                if preferred and preferred.lower() in valid_names:
                    data["practitioner"] = preferred
                else:
                    data["practitioner"] = None
            # Confusion → replay step with helpful hint (don't auto-advance)
            elif any(phrase in msg_lower for phrase in CONFUSION_PHRASES):
                actions = [
                    {"label": f"{p['name']} ({p['title']})", "value": p["name"], "action_type": "booking"}
                    for p in practitioners
                ]
                actions.append({"label": "No preference", "value": "No preference", "action_type": "booking"})
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "practitioner_confused", actions
            elif msg_lower in ("no preference",) or msg_words & {
                "any", "anyone", "anybody", "either", "whoever", "whichever",
                "available", "earliest", "first",
            } or any(p in msg_lower for p in (
                "no preference", "don't mind", "dont mind", "doesn't matter",
                "doesnt matter", "don't care", "dont care", "up to you",
                "you choose", "you pick", "any of them", "either one",
                "whoever is available", "no particular",
            )):
                data["practitioner"] = None
            elif msg_lower in valid_names:
                # Exact match — use properly-cased name
                for p in practitioners:
                    if message.strip().lower() == p["name"].lower():
                        data["practitioner"] = p["name"]
                        break
            else:
                # Partial name match: "Dr Ali", "Ali", "Nurani", etc.
                partial_matches = []
                for p in practitioners:
                    p_lower = p["name"].lower()
                    # Check if input is a substring of the name or vice versa
                    if msg_lower in p_lower or p_lower in msg_lower:
                        partial_matches.append(p)
                    else:
                        # Check if any user word matches a name part
                        # (ignore common titles like "dr", "dr.")
                        user_words = {w.rstrip(".") for w in msg_lower.split()} - {"dr", "i", "want", "with"}
                        name_parts = {w.rstrip(".").lower() for w in p["name"].split()}
                        if user_words & name_parts:
                            partial_matches.append(p)
                if len(partial_matches) == 1:
                    data["practitioner"] = partial_matches[0]["name"]
                elif len(partial_matches) > 1:
                    # Ambiguous — show only the matching practitioners
                    actions = [
                        {"label": f"{p['name']} ({p['title']})", "value": p["name"], "action_type": "booking"}
                        for p in partial_matches
                    ]
                    actions.append({"label": "No preference", "value": "No preference", "action_type": "booking"})
                    actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                    return "ambiguous_practitioner", actions
                else:
                    # Invalid choice — retry
                    actions = [
                        {"label": f"{p['name']} ({p['title']})", "value": p["name"], "action_type": "booking"}
                        for p in practitioners
                    ]
                    actions.append({"label": "No preference", "value": "No preference", "action_type": "booking"})
                    actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                    return "invalid_practitioner", actions

            data["state"] = "select_date"
            await self._set_state(session_id, data)

            dates = self._available_dates()
            actions = [
                {"label": self._format_date(d), "value": d, "action_type": "booking"} for d in dates
            ]
            actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
            return "select_date", actions

        # ── select_date ────────────────────────────────────────
        if state == "select_date":
            msg_lower = message.strip().lower()

            # "Earlier dates" → go back one page (check BEFORE "later" to avoid conflict)
            if "earlier" in msg_lower and data.get("date_offset", 0) > 0:
                current_offset = max(data.get("date_offset", 0) - 5, 0)
                data["date_offset"] = current_offset
                await self._set_state(session_id, data)
                dates = self._available_dates(offset=current_offset)
                actions = [
                    {"label": self._format_date(d), "value": d, "action_type": "booking"} for d in dates
                ]
                actions.append({"label": "More Dates", "value": "Show more dates", "action_type": "quick_reply"})
                if current_offset > 0:
                    actions.append({"label": "Earlier Dates", "value": "earlier dates", "action_type": "quick_reply"})
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "select_date", actions

            # "Later" / "more dates" → show next batch
            _LATER_PHRASES = (
                "later", "more dates", "next week", "further", "other dates",
                "anything else", "something else", "different date", "not these",
                "none of these", "show more",
            )
            if any(phrase in msg_lower for phrase in _LATER_PHRASES):
                current_offset = data.get("date_offset", 0) + 5
                data["date_offset"] = current_offset
                await self._set_state(session_id, data)
                dates = self._available_dates(offset=current_offset)
                actions = [
                    {"label": self._format_date(d), "value": d, "action_type": "booking"} for d in dates
                ]
                actions.append({"label": "More Dates", "value": "Show more dates", "action_type": "quick_reply"})
                actions.append({"label": "Earlier Dates", "value": "earlier dates", "action_type": "quick_reply"})
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "select_date_later", actions

            # Try exact ISO format first, then natural language matching
            chosen_iso = None
            try:
                chosen_date = datetime.strptime(message.strip(), "%Y-%m-%d").date()
                if chosen_date <= date.today():
                    raise ValueError("Past date")
                chosen_iso = message.strip()
            except ValueError:
                # Try matching natural language against available dates
                offset = data.get("date_offset", 0)
                available = self._available_dates(offset=offset)
                chosen_iso = self._match_natural_date(msg_lower, available)

            if not chosen_iso:
                offset = data.get("date_offset", 0)
                dates = self._available_dates(offset=offset)
                actions = [
                    {"label": self._format_date(d), "value": d, "action_type": "booking"} for d in dates
                ]
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "invalid_date", actions

            data["date"] = chosen_iso
            data["state"] = "select_time"
            await self._set_state(session_id, data)

            times = self._available_times()
            actions = [
                {"label": t, "value": t, "action_type": "booking"} for t in times
            ]
            actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
            return "select_time", actions

        # ── select_time ────────────────────────────────────────
        if state == "select_time":
            valid_times = self._available_times()
            chosen_time = message.strip() if message.strip() in valid_times else None

            # Try natural language time matching: "16", "4 pm", "4pm", "2:00", etc.
            if not chosen_time:
                chosen_time = self._match_natural_time(message.strip().lower(), valid_times)

            if not chosen_time:
                # Try natural language time preference (morning/afternoon/evening)
                suggested = self._parse_time_preference(message, valid_times)
                if suggested:
                    actions = [
                        {"label": t, "value": t, "action_type": "booking"} for t in suggested
                    ]
                    actions.append({"label": "Show All Times", "value": "show all times", "action_type": "quick_reply"})
                    actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                    return "suggest_time", actions

                # "show all times" resets to full list
                if "all time" in message.strip().lower():
                    actions = [
                        {"label": t, "value": t, "action_type": "booking"} for t in valid_times
                    ]
                    actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                    return "select_time", actions

                actions = [
                    {"label": t, "value": t, "action_type": "booking"} for t in valid_times
                ]
                actions.append({"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"})
                return "invalid_time", actions

            data["time"] = chosen_time

            # Skip name/phone collection if pre-filled (verified patient)
            if data.get("name") and data.get("phone"):
                data["state"] = "confirm"
                await self._set_state(session_id, data)
                actions = [
                    {"label": "Confirm Booking", "value": "confirm", "action_type": "booking"},
                    {"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"},
                ]
                return "confirm_prefilled", actions

            data["state"] = "collect_name"
            await self._set_state(session_id, data)
            return "collect_name", [
                {"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"}
            ]

        # ── collect_name ───────────────────────────────────────
        if state == "collect_name":
            name = message.strip()
            if len(name) < 2:
                return "invalid_name", [
                    {"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"}
                ]
            data["name"] = name
            data["state"] = "collect_phone"
            await self._set_state(session_id, data)
            return "collect_phone", [
                {"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"}
            ]

        # ── collect_phone ──────────────────────────────────────
        if state == "collect_phone":
            phone = message.strip()
            # Simple validation: at least 7 digits
            digits = "".join(c for c in phone if c.isdigit())
            if len(digits) < 7:
                return "invalid_phone", [
                    {"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"}
                ]
            data["phone"] = phone
            data["state"] = "confirm"
            await self._set_state(session_id, data)

            actions = [
                {"label": "Confirm Booking", "value": "confirm", "action_type": "booking"},
                {"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"},
            ]
            return "confirm", actions

        # ── confirm ────────────────────────────────────────────
        if state == "confirm":
            msg = message.strip().lower()
            _CONFIRM_CANCEL = {"no", "n", "cancel", "nope", "nah", "not yet", "changed my mind"}
            if msg in _CONFIRM_CANCEL:
                await self._clear_state(session_id)
                return "cancelled", []
            _CONFIRM_ACCEPT = {"confirm", "yes", "y", "yeah", "yep", "yea", "sure",
                               "ok", "okay", "perfect", "absolutely", "go ahead",
                               "looks good", "sounds good", "correct", "confirmed"}
            if msg not in _CONFIRM_ACCEPT:
                actions = [
                    {"label": "Confirm Booking", "value": "confirm", "action_type": "booking"},
                    {"label": "Cancel", "value": "Cancel", "action_type": "quick_reply"},
                ]
                return "confirm", actions

            # Create appointment record
            try:
                appt = Appointment(
                    patient_name=data["name"],
                    phone=data["phone"],
                    service=data["service"],
                    practitioner=data.get("practitioner"),
                    delivery_mode=data.get("delivery_mode"),
                    appointment_date=datetime.strptime(data["date"], "%Y-%m-%d").date(),
                    appointment_time=datetime.strptime(data["time"], "%H:%M").time(),
                    status=AppointmentStatus.pending,
                    session_id=session_id,
                )
                db.add(appt)
                await db.commit()
                logger.info(f"Appointment created for {data['name']} on {data['date']} at {data['time']}")
            except Exception as e:
                logger.error(f"Failed to create appointment: {e}")
                await db.rollback()
                await self._clear_state(session_id)
                return "booking_error", []

            await self._clear_state(session_id)
            return "booked", [
                {"label": "What to Bring", "value": "What should I bring to my appointment?", "action_type": "quick_reply"},
                {"label": "Our Hours", "value": "What are your hours of operation?", "action_type": "quick_reply"},
                {"label": "Where Are You?", "value": "Where is the clinic located?", "action_type": "quick_reply"},
            ]

        # fallback — shouldn't happen
        await self._clear_state(session_id)
        return "idle", []

    def get_booking_summary(self, data: Dict) -> Dict:
        """Return a summary dict of current booking data for display."""
        raw_date = data.get("date", "")
        summary = {
            "service": data.get("service_display") or data.get("service", ""),
            "date": self._format_date(raw_date) if raw_date else "",
            "time": data.get("time", ""),
            "name": data.get("name", ""),
            "phone": data.get("phone", ""),
        }
        if data.get("practitioner"):
            summary["practitioner"] = data["practitioner"]
        if data.get("preferred_practitioner"):
            summary["preferred_practitioner"] = data["preferred_practitioner"]
        if data.get("delivery_mode"):
            summary["delivery_mode"] = data["delivery_mode"]
        return summary
