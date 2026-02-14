import json
import logging
from datetime import datetime, timedelta, date, time
from typing import Optional, Tuple, List, Dict
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings, get_practitioners_for_service
from app.models.appointment import Appointment, AppointmentStatus

logger = logging.getLogger(__name__)

# Booking states
STATES = [
    "idle",
    "select_service",
    "select_practitioner",
    "select_date",
    "select_time",
    "collect_name",
    "collect_phone",
    "confirm",
    "booked",
]

BOOKING_TRIGGERS = [
    "book", "appointment", "schedule", "reserve", "booking",
    "sign up", "sign me up", "make an appointment",
]

CONFUSION_PHRASES = [
    "don't know", "dont know", "not sure", "unsure", "confused",
    "help me", "recommend", "what should", "no idea", "which one",
    "i'm not", "im not", "suggest", "idk", "hmm", "what do you",
    "what are my", "options", "who are", "tell me more",
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
            actions = [{"label": s, "value": s, "action_type": "booking"} for s in self.services]
            actions.append({"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"})
            return "select_service", actions

        if state == "select_practitioner":
            service = data.get("service", "")
            practitioners = get_practitioners_for_service(service)
            actions = [
                {"label": f"{p['name']} ({p['title']})", "value": p["name"], "action_type": "booking"}
                for p in practitioners
            ]
            actions.append({"label": "No preference", "value": "__no_preference__", "action_type": "booking"})
            actions.append({"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"})
            return "select_practitioner", actions

        if state == "select_date":
            dates = self._available_dates()
            actions = [
                {"label": self._format_date(d), "value": d, "action_type": "booking"} for d in dates
            ]
            actions.append({"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"})
            return "select_date", actions

        if state == "select_time":
            times = self._available_times()
            actions = [
                {"label": t, "value": t, "action_type": "booking"} for t in times
            ]
            actions.append({"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"})
            return "select_time", actions

        if state == "collect_name":
            return "collect_name", [
                {"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"}
            ]

        if state == "collect_phone":
            return "collect_phone", [
                {"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"}
            ]

        if state == "confirm":
            return "confirm", [
                {"label": "Confirm Booking", "value": "__confirm__", "action_type": "booking"},
                {"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"},
            ]

        return "idle", []

    # ── intent detection ───────────────────────────────────────────

    @staticmethod
    def is_booking_intent(message: str) -> bool:
        msg = message.lower()
        return any(trigger in msg for trigger in BOOKING_TRIGGERS)

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
    def _available_dates() -> List[str]:
        """Return next 5 weekdays starting from tomorrow."""
        dates = []
        d = date.today() + timedelta(days=1)
        while len(dates) < 5:
            if d.weekday() < 5:  # Mon-Fri
                dates.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=1)
        return dates

    @staticmethod
    def _available_times() -> List[str]:
        """Return hourly slots between booking_hours_start and booking_hours_end."""
        slots = []
        for h in range(settings.booking_hours_start, settings.booking_hours_end):
            slots.append(f"{h:02d}:00")
        return slots

    # ── main entry point ───────────────────────────────────────────

    async def start(self, session_id: str) -> Tuple[str, List[Dict]]:
        """Start the booking flow. Returns (step_hint, actions)."""
        await self._set_state(session_id, {"state": "select_service"})
        actions = [{"label": s, "value": s, "action_type": "booking"} for s in self.services]
        actions.append({"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"})
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
        if message.strip().lower() in ("cancel", "__cancel__"):
            await self._clear_state(session_id)
            return "cancelled", []

        # "Continue" — re-show current step options
        if message.strip().lower() == "continue":
            return await self._replay_step(session_id, data)

        # ── select_service ─────────────────────────────────────
        if state == "select_service":
            msg_lower = message.strip().lower()

            # Detect confusion → recommend Initial Consultation
            if any(phrase in msg_lower for phrase in CONFUSION_PHRASES):
                actions = [
                    {"label": "Initial Consultation", "value": "Initial Consultation", "action_type": "booking"},
                    {"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"},
                ]
                return "recommend_consult", actions

            # Validate service
            chosen = None
            for svc in self.services:
                if msg_lower == svc.lower():
                    chosen = svc
                    break
            if not chosen:
                # retry
                actions = [{"label": s, "value": s, "action_type": "booking"} for s in self.services]
                actions.append({"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"})
                return "invalid_service", actions

            data["service"] = chosen
            practitioners = get_practitioners_for_service(chosen)

            # Skip practitioner step if no practitioners offer this service
            if not practitioners:
                data["practitioner"] = None
                data["state"] = "select_date"
                await self._set_state(session_id, data)

                dates = self._available_dates()
                actions = [
                    {"label": self._format_date(d), "value": d, "action_type": "booking"} for d in dates
                ]
                actions.append({"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"})
                return "select_date", actions

            data["state"] = "select_practitioner"
            await self._set_state(session_id, data)

            actions = [
                {"label": f"{p['name']} ({p['title']})", "value": p["name"], "action_type": "booking"}
                for p in practitioners
            ]
            actions.append({"label": "No preference", "value": "__no_preference__", "action_type": "booking"})
            actions.append({"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"})
            return "select_practitioner", actions

        # ── select_practitioner ────────────────────────────────
        if state == "select_practitioner":
            msg_lower = message.strip().lower()
            service = data.get("service", "")
            practitioners = get_practitioners_for_service(service)
            valid_names = [p["name"].lower() for p in practitioners]

            # Confusion → treat as no preference
            if any(phrase in msg_lower for phrase in CONFUSION_PHRASES):
                data["practitioner"] = None
            elif msg_lower in ("no preference", "__no_preference__"):
                data["practitioner"] = None
            elif msg_lower in valid_names:
                # Match the properly-cased name
                for p in practitioners:
                    if message.strip().lower() == p["name"].lower():
                        data["practitioner"] = p["name"]
                        break
            else:
                # Invalid choice — retry
                actions = [
                    {"label": f"{p['name']} ({p['title']})", "value": p["name"], "action_type": "booking"}
                    for p in practitioners
                ]
                actions.append({"label": "No preference", "value": "__no_preference__", "action_type": "booking"})
                actions.append({"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"})
                return "invalid_practitioner", actions

            data["state"] = "select_date"
            await self._set_state(session_id, data)

            dates = self._available_dates()
            actions = [
                {"label": self._format_date(d), "value": d, "action_type": "booking"} for d in dates
            ]
            actions.append({"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"})
            return "select_date", actions

        # ── select_date ────────────────────────────────────────
        if state == "select_date":
            try:
                chosen_date = datetime.strptime(message.strip(), "%Y-%m-%d").date()
                if chosen_date <= date.today():
                    raise ValueError("Past date")
            except ValueError:
                dates = self._available_dates()
                actions = [
                    {"label": self._format_date(d), "value": d, "action_type": "booking"} for d in dates
                ]
                actions.append({"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"})
                return "invalid_date", actions

            data["date"] = message.strip()
            data["state"] = "select_time"
            await self._set_state(session_id, data)

            times = self._available_times()
            actions = [
                {"label": t, "value": t, "action_type": "booking"} for t in times
            ]
            actions.append({"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"})
            return "select_time", actions

        # ── select_time ────────────────────────────────────────
        if state == "select_time":
            valid_times = self._available_times()
            if message.strip() not in valid_times:
                actions = [
                    {"label": t, "value": t, "action_type": "booking"} for t in valid_times
                ]
                actions.append({"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"})
                return "invalid_time", actions

            data["time"] = message.strip()
            data["state"] = "collect_name"
            await self._set_state(session_id, data)
            return "collect_name", [
                {"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"}
            ]

        # ── collect_name ───────────────────────────────────────
        if state == "collect_name":
            name = message.strip()
            if len(name) < 2:
                return "invalid_name", [
                    {"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"}
                ]
            data["name"] = name
            data["state"] = "collect_phone"
            await self._set_state(session_id, data)
            return "collect_phone", [
                {"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"}
            ]

        # ── collect_phone ──────────────────────────────────────
        if state == "collect_phone":
            phone = message.strip()
            # Simple validation: at least 7 digits
            digits = "".join(c for c in phone if c.isdigit())
            if len(digits) < 7:
                return "invalid_phone", [
                    {"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"}
                ]
            data["phone"] = phone
            data["state"] = "confirm"
            await self._set_state(session_id, data)

            actions = [
                {"label": "Confirm Booking", "value": "__confirm__", "action_type": "booking"},
                {"label": "Cancel", "value": "__cancel__", "action_type": "quick_reply"},
            ]
            return "confirm", actions

        # ── confirm ────────────────────────────────────────────
        if state == "confirm":
            if message.strip().lower() not in ("confirm", "__confirm__", "yes", "y"):
                await self._clear_state(session_id)
                return "cancelled", []

            # Create appointment record
            try:
                appt = Appointment(
                    patient_name=data["name"],
                    phone=data["phone"],
                    service=data["service"],
                    practitioner=data.get("practitioner"),
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
            return "booked", []

        # fallback — shouldn't happen
        await self._clear_state(session_id)
        return "idle", []

    def get_booking_summary(self, data: Dict) -> Dict:
        """Return a summary dict of current booking data for display."""
        raw_date = data.get("date", "")
        summary = {
            "service": data.get("service", ""),
            "date": self._format_date(raw_date) if raw_date else "",
            "time": data.get("time", ""),
            "name": data.get("name", ""),
            "phone": data.get("phone", ""),
        }
        if data.get("practitioner"):
            summary["practitioner"] = data["practitioner"]
        return summary
