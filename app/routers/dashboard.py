from fastapi import APIRouter, Query, Cookie, Response
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select, func, case, cast, Date
from collections import defaultdict
from typing import Optional
from datetime import datetime, timedelta, timezone

from app.database import AsyncSessionLocal
from app.models.analytics import ChatAnalytics
from app.models.database import Feedback
from app.models.appointment import Appointment, AppointmentStatus
from app.config import settings

router = APIRouter()

# ── Auth helpers ──────────────────────────────────────────────────

_COOKIE_NAME = "dashboard_key"


def _check_auth(key: Optional[str], cookie: Optional[str]) -> bool:
    """Return True if the key or cookie matches the dashboard password."""
    pwd = settings.dashboard_password
    return (key and key == pwd) or (cookie and cookie == pwd)


def _period_filter(period: str):
    """Return a SQLAlchemy filter clause for the given period."""
    now = datetime.now(timezone.utc)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7d":
        start = now - timedelta(days=7)
    elif period == "30d":
        start = now - timedelta(days=30)
    else:
        return None  # "all"
    return ChatAnalytics.created_at >= start


def _appointment_period_filter(period: str):
    """Return a SQLAlchemy filter clause for Appointment.created_at."""
    now = datetime.now(timezone.utc)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7d":
        start = now - timedelta(days=7)
    elif period == "30d":
        start = now - timedelta(days=30)
    else:
        return None  # "all"
    return Appointment.created_at >= start


# ── API endpoints ─────────────────────────────────────────────────

@router.get("/dashboard/api/overview")
async def api_overview(
    period: str = Query("7d", regex="^(today|7d|30d|all)$"),
    dashboard_key: Optional[str] = Cookie(None),
    key: Optional[str] = Query(None),
):
    if not _check_auth(key, dashboard_key):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    pf = _period_filter(period)
    async with AsyncSessionLocal() as db:
        q = select(
            func.count(ChatAnalytics.id).label("total"),
            func.sum(case((ChatAnalytics.response_source == "cache_hit", 1), else_=0)).label("cache_hits"),
            func.sum(case((ChatAnalytics.response_source == "llm", 1), else_=0)).label("llm_calls"),
            func.sum(case((ChatAnalytics.is_knowledge_gap.is_(True), 1), else_=0)).label("knowledge_gaps"),
            func.sum(case((ChatAnalytics.confidence == "high", 1), else_=0)).label("high_conf"),
            func.sum(case((ChatAnalytics.confidence == "medium", 1), else_=0)).label("med_conf"),
            func.sum(case((ChatAnalytics.confidence == "low", 1), else_=0)).label("low_conf"),
            func.avg(ChatAnalytics.response_time_ms).label("avg_latency"),
            func.sum(case((ChatAnalytics.sentiment == "positive", 1), else_=0)).label("sent_pos"),
            func.sum(case((ChatAnalytics.sentiment == "neutral", 1), else_=0)).label("sent_neu"),
            func.sum(case((ChatAnalytics.sentiment == "negative", 1), else_=0)).label("sent_neg"),
        )
        if pf is not None:
            q = q.where(pf)
        row = (await db.execute(q)).one()

        total = row.total or 0
        cache_hits = row.cache_hits or 0
        llm_calls = row.llm_calls or 0
        knowledge_gaps = row.knowledge_gaps or 0
        high = row.high_conf or 0
        med = row.med_conf or 0
        low = row.low_conf or 0
        conf_total = high + med + low

        return {
            "total_chats": total,
            "cache_hit_pct": round(cache_hits / total * 100, 1) if total else 0,
            "llm_calls": llm_calls,
            "knowledge_gaps": knowledge_gaps,
            "avg_confidence": round((high * 3 + med * 2 + low * 1) / conf_total, 2) if conf_total else 0,
            "avg_latency_ms": round(row.avg_latency) if row.avg_latency else 0,
            "sentiment_distribution": {
                "positive": row.sent_pos or 0,
                "neutral": row.sent_neu or 0,
                "negative": row.sent_neg or 0,
            },
        }


@router.get("/dashboard/api/source-distribution")
async def api_source_distribution(
    period: str = Query("7d", regex="^(today|7d|30d|all)$"),
    dashboard_key: Optional[str] = Cookie(None),
    key: Optional[str] = Query(None),
):
    if not _check_auth(key, dashboard_key):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    pf = _period_filter(period)
    async with AsyncSessionLocal() as db:
        q = (
            select(
                ChatAnalytics.response_source,
                func.count(ChatAnalytics.id).label("count"),
            )
            .group_by(ChatAnalytics.response_source)
        )
        if pf is not None:
            q = q.where(pf)
        rows = (await db.execute(q)).all()
        return {r.response_source: r.count for r in rows}


@router.get("/dashboard/api/conversations-over-time")
async def api_conversations_over_time(
    period: str = Query("7d", regex="^(today|7d|30d|all)$"),
    dashboard_key: Optional[str] = Cookie(None),
    key: Optional[str] = Query(None),
):
    if not _check_auth(key, dashboard_key):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    pf = _period_filter(period)
    async with AsyncSessionLocal() as db:
        q = (
            select(
                cast(ChatAnalytics.created_at, Date).label("day"),
                func.count(ChatAnalytics.id).label("count"),
            )
            .group_by("day")
            .order_by("day")
        )
        if pf is not None:
            q = q.where(pf)
        rows = (await db.execute(q)).all()
        return [{"date": str(r.day), "count": r.count} for r in rows]


@router.get("/dashboard/api/conversations")
async def api_conversations(
    page: int = Query(1, ge=1),
    period: str = Query("7d", regex="^(today|7d|30d|all)$"),
    dashboard_key: Optional[str] = Cookie(None),
    key: Optional[str] = Query(None),
):
    if not _check_auth(key, dashboard_key):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    per_page = 20
    offset = (page - 1) * per_page
    pf = _period_filter(period)

    async with AsyncSessionLocal() as db:
        count_q = select(func.count(ChatAnalytics.id))
        data_q = (
            select(ChatAnalytics)
            .order_by(ChatAnalytics.created_at.desc())
            .limit(per_page)
            .offset(offset)
        )
        if pf is not None:
            count_q = count_q.where(pf)
            data_q = data_q.where(pf)

        total = (await db.execute(count_q)).scalar() or 0
        rows = (await db.execute(data_q)).scalars().all()

        return {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
            "items": [
                {
                    "id": r.id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "session_id": r.session_id[:8] + "..." if r.session_id else "",
                    "full_session_id": r.session_id or "",
                    "question": r.question[:120],
                    "answer": r.answer[:120],
                    "response_source": r.response_source,
                    "route_taken": r.route_taken,
                    "confidence": r.confidence,
                    "max_similarity": round(r.max_similarity, 3) if r.max_similarity else None,
                    "chunk_count": r.chunk_count,
                    "is_knowledge_gap": r.is_knowledge_gap,
                    "patient_type": r.patient_type,
                    "response_time_ms": r.response_time_ms,
                }
                for r in rows
            ],
        }


@router.get("/dashboard/api/sessions")
async def api_sessions(
    page: int = Query(1, ge=1),
    period: str = Query("7d", regex="^(today|7d|30d|all)$"),
    dashboard_key: Optional[str] = Cookie(None),
    key: Optional[str] = Query(None),
):
    if not _check_auth(key, dashboard_key):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    per_page = 20
    offset = (page - 1) * per_page
    pf = _period_filter(period)

    async with AsyncSessionLocal() as db:
        # 1. Count distinct sessions
        count_q = select(func.count(func.distinct(ChatAnalytics.session_id)))
        if pf is not None:
            count_q = count_q.where(pf)
        total = (await db.execute(count_q)).scalar() or 0

        # 2. Paginate session IDs by most recent activity
        page_q = (
            select(
                ChatAnalytics.session_id,
                func.max(ChatAnalytics.created_at).label("last_at"),
            )
            .group_by(ChatAnalytics.session_id)
            .order_by(func.max(ChatAnalytics.created_at).desc())
            .limit(per_page)
            .offset(offset)
        )
        if pf is not None:
            page_q = page_q.where(pf)
        page_rows = (await db.execute(page_q)).all()
        session_ids = [r.session_id for r in page_rows]

        if not session_ids:
            return {
                "page": page, "per_page": per_page, "total": total,
                "pages": (total + per_page - 1) // per_page if total else 0,
                "items": [],
            }

        # 3a. Fetch all analytics rows for these sessions
        detail_q = (
            select(ChatAnalytics)
            .where(ChatAnalytics.session_id.in_(session_ids))
            .order_by(ChatAnalytics.created_at.asc())
        )
        all_msgs = (await db.execute(detail_q)).scalars().all()

        # 3b. Feedback summary per session
        fb_q = (
            select(
                Feedback.session_id,
                func.sum(case((Feedback.rating == 1, 1), else_=0)).label("thumbs_up"),
                func.sum(case((Feedback.rating == -1, 1), else_=0)).label("thumbs_down"),
            )
            .where(Feedback.session_id.in_(session_ids))
            .group_by(Feedback.session_id)
        )
        fb_rows = (await db.execute(fb_q)).all()
        fb_map = {r.session_id: {"up": r.thumbs_up or 0, "down": r.thumbs_down or 0} for r in fb_rows}

    # Group messages by session in Python
    sessions = defaultdict(list)
    for m in all_msgs:
        sessions[m.session_id].append(m)

    items = []
    for sid in session_ids:
        msgs = sessions.get(sid, [])
        if not msgs:
            continue

        msg_count = len(msgs)
        first_q = msgs[0].question[:120] if msgs[0].question else ""
        patient_type = msgs[0].patient_type or "unknown"
        started_at = msgs[0].created_at
        last_at = msgs[-1].created_at
        avg_latency = round(
            sum(m.response_time_ms or 0 for m in msgs) / msg_count
        )
        knowledge_gaps = sum(1 for m in msgs if m.is_knowledge_gap)

        # Feedback for this session
        fb = fb_map.get(sid)

        # Sentiment from stored LLM analysis
        pos = sum(1 for m in msgs if m.sentiment == "positive")
        neu = sum(1 for m in msgs if m.sentiment == "neutral")
        neg = sum(1 for m in msgs if m.sentiment == "negative")
        sent_total = pos + neu + neg

        if sent_total > 0:
            sentiment_score = round((pos * 100 + neu * 50 + neg * 0) / sent_total, 1)
            if pos >= neu and pos >= neg:
                sentiment_label = "positive"
            elif neg >= pos and neg >= neu:
                sentiment_label = "negative"
            else:
                sentiment_label = "neutral"
        else:
            # Fallback for pre-migration rows without sentiment
            high = sum(1 for m in msgs if m.confidence == "high")
            med = sum(1 for m in msgs if m.confidence == "medium")
            low = sum(1 for m in msgs if m.confidence == "low")
            conf_total = high + med + low
            if fb and (fb["up"] + fb["down"]) > 0:
                sentiment_score = round(fb["up"] / (fb["up"] + fb["down"]) * 100, 1)
            elif conf_total > 0:
                sentiment_score = round((high * 3 + med * 2 + low * 1) / conf_total * 33.3, 1)
            else:
                sentiment_score = None
            if sentiment_score is None:
                sentiment_label = "none"
            elif sentiment_score >= 70:
                sentiment_label = "positive"
            elif sentiment_score >= 40:
                sentiment_label = "neutral"
            else:
                sentiment_label = "negative"

        items.append({
            "session_id": sid,
            "session_id_short": sid[:8] + "..." if sid and len(sid) > 8 else sid,
            "started_at": started_at.isoformat() if started_at else None,
            "last_message_at": last_at.isoformat() if last_at else None,
            "message_count": msg_count,
            "patient_type": patient_type,
            "first_question": first_q,
            "avg_latency_ms": avg_latency,
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
            "thumbs_up": fb["up"] if fb else 0,
            "thumbs_down": fb["down"] if fb else 0,
            "knowledge_gaps": knowledge_gaps,
        })

    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page,
        "items": items,
    }


@router.get("/dashboard/api/csat-trend")
async def api_csat_trend(
    period: str = Query("7d", regex="^(today|7d|30d|all)$"),
    dashboard_key: Optional[str] = Cookie(None),
    key: Optional[str] = Query(None),
):
    if not _check_auth(key, dashboard_key):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    pf_fb = None
    now = datetime.now(timezone.utc)
    if period == "today":
        pf_fb = Feedback.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7d":
        pf_fb = Feedback.created_at >= now - timedelta(days=7)
    elif period == "30d":
        pf_fb = Feedback.created_at >= now - timedelta(days=30)

    async with AsyncSessionLocal() as db:
        q = (
            select(
                cast(Feedback.created_at, Date).label("day"),
                func.count(Feedback.id).label("total"),
                func.sum(case((Feedback.rating == 1, 1), else_=0)).label("thumbs_up"),
                func.sum(case((Feedback.rating == -1, 1), else_=0)).label("thumbs_down"),
            )
            .group_by("day")
            .order_by("day")
        )
        if pf_fb is not None:
            q = q.where(pf_fb)
        rows = (await db.execute(q)).all()

        return [
            {
                "date": str(r.day),
                "satisfaction_pct": round((r.thumbs_up or 0) / r.total * 100, 1) if r.total else 0,
                "thumbs_up": r.thumbs_up or 0,
                "thumbs_down": r.thumbs_down or 0,
            }
            for r in rows
        ]


@router.get("/dashboard/api/session/{session_id}")
async def api_session_detail(
    session_id: str,
    dashboard_key: Optional[str] = Cookie(None),
    key: Optional[str] = Query(None),
):
    if not _check_auth(key, dashboard_key):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    async with AsyncSessionLocal() as db:
        msg_q = (
            select(ChatAnalytics)
            .where(ChatAnalytics.session_id == session_id)
            .order_by(ChatAnalytics.created_at.asc())
        )
        messages = (await db.execute(msg_q)).scalars().all()

        fb_q = (
            select(Feedback)
            .where(Feedback.session_id == session_id)
            .order_by(Feedback.created_at.asc())
        )
        feedback = (await db.execute(fb_q)).scalars().all()

        return {
            "session_id": session_id,
            "messages": [
                {
                    "id": m.id,
                    "question": m.question,
                    "answer": m.answer,
                    "response_source": m.response_source,
                    "route_taken": m.route_taken,
                    "confidence": m.confidence,
                    "max_similarity": round(m.max_similarity, 3) if m.max_similarity else None,
                    "chunk_count": m.chunk_count,
                    "is_knowledge_gap": m.is_knowledge_gap,
                    "patient_type": m.patient_type,
                    "sentiment": m.sentiment,
                    "response_time_ms": m.response_time_ms,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in messages
            ],
            "feedback": [
                {
                    "id": f.id,
                    "question": f.question,
                    "rating": f.rating,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                }
                for f in feedback
            ],
        }


@router.get("/dashboard/api/knowledge-gaps")
async def api_knowledge_gaps(
    page: int = Query(1, ge=1),
    period: str = Query("7d", regex="^(today|7d|30d|all)$"),
    dashboard_key: Optional[str] = Cookie(None),
    key: Optional[str] = Query(None),
):
    if not _check_auth(key, dashboard_key):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    per_page = 20
    offset = (page - 1) * per_page
    pf = _period_filter(period)

    async with AsyncSessionLocal() as db:
        base = ChatAnalytics.is_knowledge_gap.is_(True)
        count_q = select(func.count(ChatAnalytics.id)).where(base)
        data_q = (
            select(ChatAnalytics)
            .where(base)
            .order_by(ChatAnalytics.created_at.desc())
            .limit(per_page)
            .offset(offset)
        )
        if pf is not None:
            count_q = count_q.where(pf)
            data_q = data_q.where(pf)

        total = (await db.execute(count_q)).scalar() or 0
        rows = (await db.execute(data_q)).scalars().all()

        return {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
            "items": [
                {
                    "id": r.id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "session_id": r.session_id[:8] + "..." if r.session_id else "",
                    "question": r.question,
                    "answer": r.answer[:200],
                    "response_source": r.response_source,
                    "max_similarity": round(r.max_similarity, 3) if r.max_similarity else None,
                    "patient_type": r.patient_type,
                    "response_time_ms": r.response_time_ms,
                }
                for r in rows
            ],
        }


@router.get("/dashboard/api/feedback-summary")
async def api_feedback_summary(
    period: str = Query("7d", regex="^(today|7d|30d|all)$"),
    dashboard_key: Optional[str] = Cookie(None),
    key: Optional[str] = Query(None),
):
    if not _check_auth(key, dashboard_key):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    pf_fb = None
    now = datetime.now(timezone.utc)
    if period == "today":
        pf_fb = Feedback.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7d":
        pf_fb = Feedback.created_at >= now - timedelta(days=7)
    elif period == "30d":
        pf_fb = Feedback.created_at >= now - timedelta(days=30)

    async with AsyncSessionLocal() as db:
        q = select(
            func.count(Feedback.id).label("total"),
            func.sum(case((Feedback.rating == 1, 1), else_=0)).label("thumbs_up"),
            func.sum(case((Feedback.rating == -1, 1), else_=0)).label("thumbs_down"),
        )
        if pf_fb is not None:
            q = q.where(pf_fb)
        row = (await db.execute(q)).one()

        total = row.total or 0
        up = row.thumbs_up or 0
        down = row.thumbs_down or 0

        return {
            "total": total,
            "thumbs_up": up,
            "thumbs_down": down,
            "satisfaction_pct": round(up / total * 100, 1) if total else 0,
        }


@router.get("/dashboard/api/booking-stats")
async def api_booking_stats(
    period: str = Query("7d", regex="^(today|7d|30d|all)$"),
    dashboard_key: Optional[str] = Cookie(None),
    key: Optional[str] = Query(None),
):
    if not _check_auth(key, dashboard_key):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    pf = _appointment_period_filter(period)
    async with AsyncSessionLocal() as db:
        q = select(
            func.count(Appointment.id).label("total"),
            func.sum(case((Appointment.status == AppointmentStatus.pending, 1), else_=0)).label("pending"),
            func.sum(case((Appointment.status == AppointmentStatus.confirmed, 1), else_=0)).label("confirmed"),
            func.sum(case((Appointment.status == AppointmentStatus.cancelled, 1), else_=0)).label("cancelled"),
            func.sum(case((Appointment.status == AppointmentStatus.completed, 1), else_=0)).label("completed"),
        )
        if pf is not None:
            q = q.where(pf)
        row = (await db.execute(q)).one()

        return {
            "total": row.total or 0,
            "pending": row.pending or 0,
            "confirmed": row.confirmed or 0,
            "cancelled": row.cancelled or 0,
            "completed": row.completed or 0,
        }


@router.get("/dashboard/api/bookings")
async def api_bookings(
    page: int = Query(1, ge=1),
    period: str = Query("7d", regex="^(today|7d|30d|all)$"),
    dashboard_key: Optional[str] = Cookie(None),
    key: Optional[str] = Query(None),
):
    if not _check_auth(key, dashboard_key):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    per_page = 20
    offset = (page - 1) * per_page
    pf = _appointment_period_filter(period)

    async with AsyncSessionLocal() as db:
        count_q = select(func.count(Appointment.id))
        data_q = (
            select(Appointment)
            .order_by(Appointment.created_at.desc())
            .limit(per_page)
            .offset(offset)
        )
        if pf is not None:
            count_q = count_q.where(pf)
            data_q = data_q.where(pf)

        total = (await db.execute(count_q)).scalar() or 0
        rows = (await db.execute(data_q)).scalars().all()

        return {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
            "items": [
                {
                    "id": r.id,
                    "patient_name": r.patient_name,
                    "phone": r.phone,
                    "email": r.email,
                    "service": r.service,
                    "practitioner": r.practitioner,
                    "delivery_mode": r.delivery_mode,
                    "appointment_date": str(r.appointment_date) if r.appointment_date else None,
                    "appointment_time": str(r.appointment_time) if r.appointment_time else None,
                    "status": r.status.value if r.status else None,
                    "session_id": r.session_id,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
        }


# ── Dashboard UI ──────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_ui(
    response: Response,
    key: Optional[str] = Query(None),
    dashboard_key: Optional[str] = Cookie(None),
):
    authed = _check_auth(key, dashboard_key)

    # Set cookie if authenticated via query param
    if key and key == settings.dashboard_password:
        response.set_cookie(_COOKIE_NAME, key, httponly=True, max_age=86400 * 7)

    if not authed:
        return _login_html()

    return _dashboard_html()


def _login_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nova Dashboard - Login</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--teal:#2a9d8f;--teal-dark:#1f7a6f;--navy:#1a4b6e;--gray-50:#f8fafc;--gray-100:#f1f5f9;--gray-200:#e2e8f0;--gray-400:#94a3b8;--gray-500:#64748b;--gray-600:#475569;--slate:#334155;--white:#fff;--radius:16px;--shadow:0 4px 6px -1px rgba(0,0,0,.07),0 2px 4px -2px rgba(0,0,0,.05);--shadow-xl:0 25px 60px -15px rgba(26,75,110,.25)}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:var(--gray-100);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px}
.card{background:var(--white);border-radius:var(--radius);box-shadow:var(--shadow-xl);padding:48px 40px;max-width:400px;width:100%;text-align:center}
.card h1{font-size:22px;color:var(--navy);margin-bottom:8px}
.card p{font-size:14px;color:var(--gray-500);margin-bottom:28px}
.card input{width:100%;padding:12px 16px;border:1.5px solid var(--gray-200);border-radius:10px;font-size:14px;font-family:inherit;outline:none;transition:border .15s;margin-bottom:16px}
.card input:focus{border-color:var(--teal)}
.card button{width:100%;padding:13px;background:linear-gradient(135deg,var(--teal),var(--teal-dark));color:var(--white);border:none;border-radius:10px;font-size:14px;font-weight:600;font-family:inherit;cursor:pointer;transition:transform .15s}
.card button:hover{transform:translateY(-1px)}
.error{color:#ef4444;font-size:13px;margin-bottom:12px;display:none}
</style>
</head>
<body>
<div class="card">
<img src="/static/logo.webp" alt="Nova" style="height:48px;border-radius:10px;margin-bottom:12px">
<h1>Nova Dashboard</h1>
<p>Enter the dashboard password to continue.</p>
<div class="error" id="err">Incorrect password. Please try again.</div>
<form onsubmit="return go()">
<input type="password" id="pwd" placeholder="Password" autofocus />
<button type="submit">Sign In</button>
</form>
</div>
<script>
function go(){
  var p=document.getElementById('pwd').value;
  if(!p)return false;
  window.location.href='/dashboard?key='+encodeURIComponent(p);
  return false;
}
</script>
</body>
</html>"""


def _dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nova Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
:root{--teal:#2a9d8f;--teal-light:#40b4a6;--teal-dark:#1f7a6f;--navy:#1a4b6e;--navy-dark:#0f3552;--slate:#334155;--gray-50:#f8fafc;--gray-100:#f1f5f9;--gray-200:#e2e8f0;--gray-300:#cbd5e1;--gray-400:#94a3b8;--gray-500:#64748b;--gray-600:#475569;--gray-700:#334155;--white:#fff;--radius:16px;--radius-sm:10px;--shadow-sm:0 1px 2px rgba(0,0,0,.05);--shadow:0 4px 6px -1px rgba(0,0,0,.07),0 2px 4px -2px rgba(0,0,0,.05);--shadow-lg:0 20px 50px -12px rgba(0,0,0,.15)}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:var(--gray-100);color:var(--slate);min-height:100vh;padding:24px}

/* ── Header ───────────────────────────────────── */
.dash-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:0;flex-wrap:wrap;gap:12px}
.dash-header h1{font-size:24px;color:var(--navy);letter-spacing:-.5px;display:flex;align-items:center;gap:10px}
.dash-header h1 img{height:32px;width:auto;border-radius:6px}
.period-btns{display:flex;gap:6px}
.period-btn{padding:7px 16px;border:1.5px solid var(--gray-200);border-radius:999px;background:var(--white);cursor:pointer;font-size:12px;font-weight:600;font-family:inherit;color:var(--gray-500);transition:all .15s}
.period-btn:hover{border-color:var(--teal);color:var(--teal)}
.period-btn.active{background:var(--teal);border-color:var(--teal);color:var(--white)}

/* ── Tab bar ──────────────────────────────────── */
.tab-bar{display:flex;gap:0;border-bottom:2px solid var(--gray-200);margin:20px 0 24px 0;overflow-x:auto;-webkit-overflow-scrolling:touch}
.tab-btn{padding:10px 20px;border:none;background:none;cursor:pointer;font-size:13px;font-weight:600;font-family:inherit;color:var(--gray-500);border-bottom:3px solid transparent;margin-bottom:-2px;transition:all .15s;white-space:nowrap}
.tab-btn:hover{color:var(--teal)}
.tab-btn.active{color:var(--teal);border-bottom-color:var(--teal)}

/* ── Tab panels ───────────────────────────────── */
.tab-panel{display:none}
.tab-panel.active{display:block}

/* ── Stat cards ───────────────────────────────── */
.stats-row{display:grid;grid-template-columns:repeat(6,1fr);gap:16px;margin-bottom:28px}
.stat-card{background:var(--white);border-radius:var(--radius-sm);padding:20px;box-shadow:var(--shadow);text-align:center;transition:transform .15s}
.stat-card:hover{transform:translateY(-2px)}
.stat-label{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--gray-400);margin-bottom:8px}
.stat-value{font-size:28px;font-weight:700;color:var(--navy);letter-spacing:-1px}
.stat-unit{font-size:12px;font-weight:500;color:var(--gray-500);margin-top:4px}

/* ── Charts row ───────────────────────────────── */
.charts-row{display:grid;grid-template-columns:1fr 2fr;gap:16px;margin-bottom:28px}
.chart-card{background:var(--white);border-radius:var(--radius-sm);padding:24px;box-shadow:var(--shadow)}
.chart-card h3{font-size:14px;font-weight:700;color:var(--navy);margin-bottom:16px}

/* ── CSAT section ────────────────────────────────── */
.csat-section{background:var(--white);border-radius:var(--radius-sm);padding:24px;box-shadow:var(--shadow);margin-bottom:28px}
.csat-section h3{font-size:14px;font-weight:700;color:var(--navy);margin-bottom:16px}
.csat-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}
.csat-card{background:var(--gray-50);border-radius:var(--radius-sm);padding:16px;text-align:center}
.csat-card .stat-value{font-size:26px;font-weight:700;color:var(--navy);letter-spacing:-1px}
.csat-card .stat-value.green{color:#16a34a}
.csat-card .stat-value.red{color:#dc2626}
.csat-card .stat-value.teal{color:var(--teal)}
.csat-chart-wrap{height:220px}

/* ── Tables ───────────────────────────────────── */
.section{background:var(--white);border-radius:var(--radius-sm);padding:24px;box-shadow:var(--shadow);margin-bottom:28px}
.section h3{font-size:14px;font-weight:700;color:var(--navy);margin-bottom:16px}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;padding:10px 12px;background:var(--gray-50);color:var(--gray-500);font-weight:700;text-transform:uppercase;letter-spacing:.4px;font-size:10px;border-bottom:2px solid var(--gray-200)}
td{padding:10px 12px;border-bottom:1px solid var(--gray-100);color:var(--gray-600)}
tr:hover td{background:var(--gray-50)}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:10px;font-weight:600}
.badge-high{background:#dcfce7;color:#166534}
.badge-medium{background:#fef9c3;color:#854d0e}
.badge-low{background:#fee2e2;color:#991b1b}
.badge-src{background:#e0f2fe;color:#0c4a6e}
.badge-gap{background:#fee2e2;color:#991b1b}
.badge-pending{background:#fef9c3;color:#854d0e}
.badge-confirmed{background:#dbeafe;color:#1e40af}
.badge-completed{background:#dcfce7;color:#166534}
.badge-cancelled{background:#fee2e2;color:#991b1b}

/* ── Knowledge gaps ───────────────────────────── */
.gap-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}
.gap-card{border:2px solid #fca5a5;border-radius:var(--radius-sm);padding:16px;background:#fff5f5}
.gap-q{font-size:13px;font-weight:600;color:var(--slate);margin-bottom:8px}
.gap-meta{font-size:11px;color:var(--gray-500)}

/* ── Pagination ───────────────────────────────── */
.pagination{display:flex;justify-content:center;gap:6px;margin-top:16px}
.page-btn{padding:6px 12px;border:1.5px solid var(--gray-200);border-radius:6px;background:var(--white);cursor:pointer;font-size:12px;font-family:inherit;color:var(--gray-500)}
.page-btn:hover{border-color:var(--teal);color:var(--teal)}
.page-btn.active{background:var(--teal);border-color:var(--teal);color:var(--white)}
.page-btn:disabled{opacity:.4;cursor:default}

/* ── Session cards ────────────────────────────── */
.session-cards{display:flex;flex-direction:column;gap:10px}
.session-card{background:var(--white);border:1.5px solid var(--gray-200);border-radius:var(--radius-sm);padding:16px 20px;cursor:pointer;transition:all .15s}
.session-card:hover{border-color:var(--teal);box-shadow:0 4px 12px rgba(42,157,143,.12);transform:translateY(-1px)}
.session-card-header{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.session-card-header code{font-size:11px;color:var(--gray-600);font-weight:600}
.session-card-header .badge{font-size:10px}
.session-card-time{margin-left:auto;font-size:11px;color:var(--gray-400);white-space:nowrap}
.session-summary{font-size:13px;color:var(--gray-600);line-height:1.5;margin-bottom:8px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}
.session-footer{display:flex;align-items:center;gap:12px;font-size:11px;color:var(--gray-400)}
.session-footer span{display:inline-flex;align-items:center;gap:3px}
.sentiment-dot{width:8px;height:8px;border-radius:50%;display:inline-block;flex-shrink:0}
.sentiment-dot.positive{background:#22c55e}
.sentiment-dot.neutral{background:#eab308}
.sentiment-dot.negative{background:#ef4444}
.sentiment-dot.none{background:var(--gray-300)}

/* ── Bookings table ──────────────────────────── */
.bookings-table-wrap{overflow-x:auto}

/* ── Loading ──────────────────────────────────── */
.loading-text{text-align:center;color:var(--gray-400);padding:40px;font-size:13px}

/* ── Session detail modal ────────────────────── */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:1000;opacity:0;pointer-events:none;transition:opacity .25s}
.modal-overlay.open{opacity:1;pointer-events:auto}
.modal-panel{position:fixed;top:0;right:-480px;width:480px;max-width:100vw;height:100vh;background:var(--white);box-shadow:-8px 0 30px rgba(0,0,0,.15);z-index:1001;display:flex;flex-direction:column;transition:right .3s ease}
.modal-overlay.open .modal-panel{right:0}
.modal-header{padding:20px 24px;border-bottom:1px solid var(--gray-200);display:flex;align-items:center;gap:12px;flex-shrink:0}
.modal-header h3{flex:1;font-size:14px;font-weight:700;color:var(--navy);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.modal-close{width:32px;height:32px;border:none;background:var(--gray-50);border-radius:50%;cursor:pointer;display:flex;align-items:center;justify-content:center;color:var(--gray-500);font-size:18px;transition:all .15s;flex-shrink:0}
.modal-close:hover{background:var(--gray-100);color:var(--slate)}
.modal-stats{display:flex;gap:10px;padding:16px 24px;border-bottom:1px solid var(--gray-100);flex-wrap:wrap;flex-shrink:0}
.modal-stat-badge{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:999px;font-size:11px;font-weight:600;background:var(--gray-50);color:var(--gray-600)}
.modal-stat-badge.teal{background:#e0f2f1;color:var(--teal-dark)}
.modal-thread{flex:1;overflow-y:auto;padding:20px 24px;display:flex;flex-direction:column;gap:16px}
.thread-q,.thread-a{max-width:92%;padding:12px 16px;border-radius:16px;font-size:13px;line-height:1.6;word-wrap:break-word;white-space:pre-wrap}
.thread-q{background:var(--navy);color:var(--white);align-self:flex-end;border-bottom-right-radius:4px}
.thread-a{background:var(--gray-50);color:var(--slate);border:1px solid var(--gray-200);align-self:flex-start;border-bottom-left-radius:4px}
.thread-meta{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.thread-meta .badge{font-size:9px;padding:2px 6px}
.thread-fb{margin-top:4px;font-size:11px;font-weight:600}
.thread-fb.positive{color:#16a34a}
.thread-fb.negative{color:#dc2626}

/* ── Responsive ───────────────────────────────── */
@media(max-width:900px){
  .stats-row{grid-template-columns:repeat(3,1fr)!important}
  .charts-row{grid-template-columns:1fr}
  .csat-cards{grid-template-columns:repeat(2,1fr)}
  .tab-bar{gap:0}
  .tab-btn{padding:10px 14px;font-size:12px}
}
@media(max-width:600px){
  .modal-panel{width:100vw}
}
@media(max-width:600px){
  body{padding:12px}
  .stats-row{grid-template-columns:repeat(2,1fr)}
  .stat-value{font-size:22px}
  .tab-btn{padding:8px 12px;font-size:11px}
}
</style>
</head>
<body>

<div class="dash-header">
  <h1><img src="/static/logo.webp" alt="Nova">Nova Dashboard</h1>
  <div class="period-btns">
    <button class="period-btn" data-p="today" onclick="setPeriod('today')">Today</button>
    <button class="period-btn active" data-p="7d" onclick="setPeriod('7d')">7d</button>
    <button class="period-btn" data-p="30d" onclick="setPeriod('30d')">30d</button>
    <button class="period-btn" data-p="all" onclick="setPeriod('all')">All</button>
  </div>
</div>

<!-- Tab bar -->
<div class="tab-bar">
  <button class="tab-btn active" data-tab="overview" onclick="switchTab('overview')">Overview</button>
  <button class="tab-btn" data-tab="conversations" onclick="switchTab('conversations')">Conversations</button>
  <button class="tab-btn" data-tab="csat" onclick="switchTab('csat')">CSAT Score</button>
  <button class="tab-btn" data-tab="gaps" onclick="switchTab('gaps')">Knowledge Gaps</button>
  <button class="tab-btn" data-tab="bookings" onclick="switchTab('bookings')">Bookings</button>
</div>

<!-- ── Tab: Overview ──────────────────────────── -->
<div class="tab-panel active" id="tab-overview">
  <div class="stats-row">
    <div class="stat-card"><div class="stat-label">Total Chats</div><div class="stat-value" id="s-total">-</div></div>
    <div class="stat-card"><div class="stat-label">Cache Hit %</div><div class="stat-value" id="s-cache">-</div><div class="stat-unit">of requests</div></div>
    <div class="stat-card"><div class="stat-label">LLM Calls</div><div class="stat-value" id="s-llm">-</div></div>
    <div class="stat-card"><div class="stat-label">Knowledge Gaps</div><div class="stat-value" id="s-gaps">-</div></div>
    <div class="stat-card"><div class="stat-label">Avg Latency</div><div class="stat-value" id="s-latency">-</div><div class="stat-unit">ms</div></div>
    <div class="stat-card"><div class="stat-label">Sentiment</div><div class="stat-value" id="s-sentiment" style="font-size:14px;line-height:1.6">-</div></div>
  </div>
  <div class="charts-row">
    <div class="chart-card"><h3>Source Distribution</h3><canvas id="donutChart"></canvas></div>
    <div class="chart-card"><h3>Daily Volume</h3><canvas id="barChart"></canvas></div>
  </div>
</div>

<!-- ── Tab: Conversations ─────────────────────── -->
<div class="tab-panel" id="tab-conversations">
  <div class="section">
    <h3>Conversation Log</h3>
    <div id="convTable"><div class="loading-text">Loading...</div></div>
    <div class="pagination" id="convPag"></div>
  </div>
</div>

<!-- ── Tab: CSAT Score ────────────────────────── -->
<div class="tab-panel" id="tab-csat">
  <div class="csat-section">
    <h3>CSAT Score</h3>
    <div class="csat-cards">
      <div class="csat-card"><div class="stat-label">CSAT</div><div class="stat-value teal" id="fb-sat">-</div><div class="stat-unit">%</div></div>
      <div class="csat-card"><div class="stat-label">Total Ratings</div><div class="stat-value" id="fb-total">-</div></div>
      <div class="csat-card"><div class="stat-label">Thumbs Up</div><div class="stat-value green" id="fb-up">-</div></div>
      <div class="csat-card"><div class="stat-label">Thumbs Down</div><div class="stat-value red" id="fb-down">-</div></div>
    </div>
    <div class="csat-chart-wrap"><canvas id="csatChart"></canvas></div>
  </div>
</div>

<!-- ── Tab: Knowledge Gaps ────────────────────── -->
<div class="tab-panel" id="tab-gaps">
  <div class="section">
    <h3>Knowledge Gaps</h3>
    <div id="gapCards"><div class="loading-text">Loading...</div></div>
    <div class="pagination" id="gapPag"></div>
  </div>
</div>

<!-- ── Tab: Bookings ─────────────────────────── -->
<div class="tab-panel" id="tab-bookings">
  <div class="stats-row" id="booking-stats-row">
    <div class="stat-card"><div class="stat-label">Total</div><div class="stat-value" id="bk-total">-</div></div>
    <div class="stat-card"><div class="stat-label">Pending</div><div class="stat-value" id="bk-pending" style="color:#854d0e">-</div></div>
    <div class="stat-card"><div class="stat-label">Confirmed</div><div class="stat-value" id="bk-confirmed" style="color:#1e40af">-</div></div>
    <div class="stat-card"><div class="stat-label">Completed</div><div class="stat-value" id="bk-completed" style="color:#166534">-</div></div>
    <div class="stat-card"><div class="stat-label">Cancelled</div><div class="stat-value" id="bk-cancelled" style="color:#991b1b">-</div></div>
  </div>
  <div class="section">
    <h3>Appointments</h3>
    <div class="bookings-table-wrap" id="bookingsTable"><div class="loading-text">Loading...</div></div>
    <div class="pagination" id="bookingPag"></div>
  </div>
</div>

<!-- Session detail modal (global) -->
<div class="modal-overlay" id="modalOverlay" onclick="if(event.target===this)closeModal()">
  <div class="modal-panel">
    <div class="modal-header">
      <h3 id="modalTitle">Session</h3>
      <button class="modal-close" onclick="closeModal()">&times;</button>
    </div>
    <div class="modal-stats" id="modalStats"></div>
    <div class="modal-thread" id="modalThread"></div>
  </div>
</div>

<script>
let period = '7d';
let activeTab = 'overview';
let tabLoaded = {};
let donutChart = null;
let barChart = null;
let csatChart = null;
let convPage = 1;
let gapPage = 1;
let bookingPage = 1;

const SRC_COLORS = {
  cache_hit:'#22c55e', llm:'#3b82f6', known_topic:'#a855f7',
  booking:'#f59e0b', fallback:'#ef4444', patient_type:'#64748b'
};

function switchTab(tab) {
  activeTab = tab;
  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tab);
  });
  document.querySelectorAll('.tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === 'tab-' + tab);
  });
  if (!tabLoaded[tab]) {
    loadTab(tab);
  }
}

function setPeriod(p) {
  period = p;
  convPage = 1;
  gapPage = 1;
  bookingPage = 1;
  tabLoaded = {};
  document.querySelectorAll('.period-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.p === p);
  });
  loadTab(activeTab);
}

function api(path) {
  return fetch('/dashboard/api/' + path + (path.includes('?') ? '&' : '?') + 'period=' + period, {credentials:'same-origin'}).then(r => r.json());
}

function esc(s) {
  var d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

function confBadge(c) {
  return '<span class="badge badge-' + c + '">' + c + '</span>';
}

function fmtTime(iso) {
  if (!iso) return '-';
  var d = new Date(iso);
  return d.toLocaleDateString('en-US', {month:'short', day:'numeric'}) + ' ' +
         d.toLocaleTimeString('en-US', {hour:'2-digit', minute:'2-digit'});
}

async function loadTab(tab) {
  try {
    if (tab === 'overview') {
      var [overview, sources, timeline] = await Promise.all([
        api('overview'),
        api('source-distribution'),
        api('conversations-over-time'),
      ]);
      renderOverview(overview, sources, timeline);
    } else if (tab === 'conversations') {
      var convos = await api('sessions?page=' + convPage);
      renderConvos(convos);
    } else if (tab === 'csat') {
      var [feedback, csatTrend] = await Promise.all([
        api('feedback-summary'),
        api('csat-trend'),
      ]);
      renderCSAT(feedback, csatTrend);
    } else if (tab === 'gaps') {
      var gaps = await api('knowledge-gaps?page=' + gapPage);
      renderGaps(gaps);
    } else if (tab === 'bookings') {
      var [bkStats, bkList] = await Promise.all([
        api('booking-stats'),
        api('bookings?page=' + bookingPage),
      ]);
      renderBookingStats(bkStats);
      renderBookings(bkList);
    }
    tabLoaded[tab] = true;
  } catch(e) {
    console.error('Tab load error:', e);
  }
}

function renderOverview(overview, sources, timeline) {
  document.getElementById('s-total').textContent = overview.total_chats.toLocaleString();
  document.getElementById('s-cache').textContent = overview.cache_hit_pct + '%';
  document.getElementById('s-llm').textContent = overview.llm_calls.toLocaleString();
  document.getElementById('s-gaps').textContent = overview.knowledge_gaps.toLocaleString();
  document.getElementById('s-latency').textContent = overview.avg_latency_ms.toLocaleString();

  var sd = overview.sentiment_distribution || {};
  document.getElementById('s-sentiment').innerHTML =
    '<span style="color:#22c55e">' + (sd.positive || 0) + ' pos</span><br>' +
    '<span style="color:#eab308">' + (sd.neutral || 0) + ' neu</span><br>' +
    '<span style="color:#ef4444">' + (sd.negative || 0) + ' neg</span>';

  var srcLabels = Object.keys(sources);
  var srcData = Object.values(sources);
  var srcColors = srcLabels.map(l => SRC_COLORS[l] || '#94a3b8');
  if (donutChart) donutChart.destroy();
  donutChart = new Chart(document.getElementById('donutChart'), {
    type: 'doughnut',
    data: {labels: srcLabels, datasets: [{data: srcData, backgroundColor: srcColors, borderWidth: 2, borderColor: '#fff'}]},
    options: {responsive: true, plugins: {legend: {position: 'bottom', labels: {font: {size: 11, family: 'Inter'}}}}}
  });

  var barLabels = timeline.map(t => t.date);
  var barData = timeline.map(t => t.count);
  if (barChart) barChart.destroy();
  barChart = new Chart(document.getElementById('barChart'), {
    type: 'bar',
    data: {labels: barLabels, datasets: [{label: 'Conversations', data: barData, backgroundColor: 'rgba(42,157,143,0.7)', borderRadius: 6}]},
    options: {responsive: true, plugins: {legend: {display: false}}, scales: {y: {beginAtZero: true, ticks: {font: {size: 10}}}, x: {ticks: {font: {size: 10}}}}}
  });
}

function renderCSAT(feedback, csatTrend) {
  document.getElementById('fb-sat').textContent = feedback.satisfaction_pct;
  document.getElementById('fb-total').textContent = feedback.total;
  document.getElementById('fb-up').textContent = feedback.thumbs_up;
  document.getElementById('fb-down').textContent = feedback.thumbs_down;

  if (csatChart) csatChart.destroy();
  var csatLabels = csatTrend.map(t => t.date);
  var csatData = csatTrend.map(t => t.satisfaction_pct);
  csatChart = new Chart(document.getElementById('csatChart'), {
    type: 'line',
    data: {
      labels: csatLabels,
      datasets: [{
        label: 'CSAT %',
        data: csatData,
        borderColor: 'rgb(42,157,143)',
        backgroundColor: 'rgba(42,157,143,0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 4,
        pointBackgroundColor: 'rgb(42,157,143)',
        borderWidth: 2,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {legend: {display: false}},
      scales: {
        y: {beginAtZero: true, max: 100, ticks: {font: {size: 10}, callback: v => v + '%'}},
        x: {ticks: {font: {size: 10}}}
      }
    }
  });
}

function renderConvos(data) {
  if (!data.items || data.items.length === 0) {
    document.getElementById('convTable').innerHTML = '<div class="loading-text">No conversations yet.</div>';
    document.getElementById('convPag').innerHTML = '';
    return;
  }
  var html = '<div class="session-cards">';
  data.items.forEach(function(r) {
    html += '<div class="session-card" onclick="openSession(\\'' + esc(r.session_id) + '\\')">';
    html += '<div class="session-card-header">';
    html += '<span class="sentiment-dot ' + esc(r.sentiment_label) + '"></span>';
    html += '<code>' + esc(r.session_id_short) + '</code>';
    html += '<span class="badge badge-src">' + esc(r.patient_type) + ' patient</span>';
    html += '<span class="badge">' + r.message_count + ' msgs</span>';
    html += '<span class="badge">' + r.avg_latency_ms + 'ms</span>';
    html += '<span class="session-card-time">' + fmtTime(r.started_at) + '</span>';
    html += '</div>';
    var summary = r.first_question || '';
    if (summary.length > 100) summary = summary.substring(0, 100) + '...';
    html += '<div class="session-summary">"' + esc(summary) + '"</div>';
    html += '<div class="session-footer">';
    var upDown = '\\u2191' + r.thumbs_up + ' \\u2193' + r.thumbs_down;
    html += '<span>' + upDown + '</span>';
    html += '<span>' + r.knowledge_gaps + ' knowledge gap' + (r.knowledge_gaps !== 1 ? 's' : '') + '</span>';
    if (r.sentiment_score !== null) {
      html += '<span>sentiment: ' + r.sentiment_score + '%</span>';
    }
    html += '</div>';
    html += '</div>';
  });
  html += '</div>';
  document.getElementById('convTable').innerHTML = html;

  var pag = '';
  pag += '<button class="page-btn" ' + (data.page <= 1 ? 'disabled' : '') + ' onclick="convPage=' + (data.page - 1) + ';loadConvos()">&laquo;</button>';
  for (var i = 1; i <= Math.min(data.pages, 5); i++) {
    pag += '<button class="page-btn ' + (i === data.page ? 'active' : '') + '" onclick="convPage=' + i + ';loadConvos()">' + i + '</button>';
  }
  if (data.pages > 5) pag += '<button class="page-btn" disabled>...</button>';
  pag += '<button class="page-btn" ' + (data.page >= data.pages ? 'disabled' : '') + ' onclick="convPage=' + (data.page + 1) + ';loadConvos()">&raquo;</button>';
  document.getElementById('convPag').innerHTML = pag;
}

function renderGaps(data) {
  if (!data.items || data.items.length === 0) {
    document.getElementById('gapCards').innerHTML = '<div class="loading-text">No knowledge gaps found.</div>';
    document.getElementById('gapPag').innerHTML = '';
    return;
  }
  var html = '<div class="gap-cards">';
  data.items.forEach(function(r) {
    html += '<div class="gap-card">';
    html += '<div class="gap-q">' + esc(r.question) + '</div>';
    html += '<div class="gap-meta">';
    html += fmtTime(r.created_at);
    html += ' &middot; <span class="badge badge-src">' + esc(r.response_source) + '</span>';
    if (r.max_similarity !== null) html += ' &middot; similarity: ' + r.max_similarity;
    html += '</div></div>';
  });
  html += '</div>';
  document.getElementById('gapCards').innerHTML = html;

  var pag = '';
  pag += '<button class="page-btn" ' + (data.page <= 1 ? 'disabled' : '') + ' onclick="gapPage=' + (data.page - 1) + ';loadGaps()">&laquo;</button>';
  for (var i = 1; i <= Math.min(data.pages, 5); i++) {
    pag += '<button class="page-btn ' + (i === data.page ? 'active' : '') + '" onclick="gapPage=' + i + ';loadGaps()">' + i + '</button>';
  }
  if (data.pages > 5) pag += '<button class="page-btn" disabled>...</button>';
  pag += '<button class="page-btn" ' + (data.page >= data.pages ? 'disabled' : '') + ' onclick="gapPage=' + (data.page + 1) + ';loadGaps()">&raquo;</button>';
  document.getElementById('gapPag').innerHTML = pag;
}

function renderBookingStats(stats) {
  document.getElementById('bk-total').textContent = (stats.total || 0).toLocaleString();
  document.getElementById('bk-pending').textContent = (stats.pending || 0).toLocaleString();
  document.getElementById('bk-confirmed').textContent = (stats.confirmed || 0).toLocaleString();
  document.getElementById('bk-completed').textContent = (stats.completed || 0).toLocaleString();
  document.getElementById('bk-cancelled').textContent = (stats.cancelled || 0).toLocaleString();
}

function renderBookings(data) {
  if (!data.items || data.items.length === 0) {
    document.getElementById('bookingsTable').innerHTML = '<div class="loading-text">No bookings found.</div>';
    document.getElementById('bookingPag').innerHTML = '';
    return;
  }
  var html = '<table><thead><tr>';
  html += '<th>Patient</th><th>Phone</th><th>Email</th><th>Service</th><th>Practitioner</th><th>Mode</th><th>Date</th><th>Time</th><th>Status</th>';
  html += '</tr></thead><tbody>';
  data.items.forEach(function(r) {
    html += '<tr>';
    html += '<td>' + esc(r.patient_name) + '</td>';
    html += '<td>' + esc(r.phone) + '</td>';
    html += '<td>' + esc(r.email || '-') + '</td>';
    html += '<td>' + esc(r.service) + '</td>';
    html += '<td>' + esc(r.practitioner || '-') + '</td>';
    html += '<td>' + esc(r.delivery_mode || '-') + '</td>';
    html += '<td>' + esc(r.appointment_date || '-') + '</td>';
    html += '<td>' + esc(r.appointment_time || '-') + '</td>';
    html += '<td><span class="badge badge-' + esc(r.status) + '">' + esc(r.status) + '</span></td>';
    html += '</tr>';
  });
  html += '</tbody></table>';
  document.getElementById('bookingsTable').innerHTML = html;

  var pag = '';
  pag += '<button class="page-btn" ' + (data.page <= 1 ? 'disabled' : '') + ' onclick="bookingPage=' + (data.page - 1) + ';loadBookings()">&laquo;</button>';
  for (var i = 1; i <= Math.min(data.pages, 5); i++) {
    pag += '<button class="page-btn ' + (i === data.page ? 'active' : '') + '" onclick="bookingPage=' + i + ';loadBookings()">' + i + '</button>';
  }
  if (data.pages > 5) pag += '<button class="page-btn" disabled>...</button>';
  pag += '<button class="page-btn" ' + (data.page >= data.pages ? 'disabled' : '') + ' onclick="bookingPage=' + (data.page + 1) + ';loadBookings()">&raquo;</button>';
  document.getElementById('bookingPag').innerHTML = pag;
}

async function loadConvos() {
  tabLoaded['conversations'] = false;
  var data = await api('sessions?page=' + convPage);
  renderConvos(data);
  tabLoaded['conversations'] = true;
}

async function loadGaps() {
  tabLoaded['gaps'] = false;
  var data = await api('knowledge-gaps?page=' + gapPage);
  renderGaps(data);
  tabLoaded['gaps'] = true;
}

async function loadBookings() {
  tabLoaded['bookings'] = false;
  var [bkStats, bkList] = await Promise.all([
    api('booking-stats'),
    api('bookings?page=' + bookingPage),
  ]);
  renderBookingStats(bkStats);
  renderBookings(bkList);
  tabLoaded['bookings'] = true;
}

async function openSession(sessionId) {
  if (!sessionId) return;
  var overlay = document.getElementById('modalOverlay');
  var thread = document.getElementById('modalThread');
  var stats = document.getElementById('modalStats');
  document.getElementById('modalTitle').textContent = 'Session ' + sessionId.substring(0,8) + '...';
  stats.innerHTML = '';
  thread.innerHTML = '<div class="loading-text">Loading session...</div>';
  overlay.classList.add('open');

  try {
    var data = await fetch('/dashboard/api/session/' + encodeURIComponent(sessionId) + '?period=' + period, {credentials:'same-origin'}).then(r => r.json());
    if (data.error) { thread.innerHTML = '<div class="loading-text">Error: ' + esc(data.error) + '</div>'; return; }

    var msgs = data.messages || [];
    var fbs = data.feedback || [];

    var fbMap = {};
    fbs.forEach(function(f) { fbMap[f.question] = f.rating; });

    var patientType = msgs.length > 0 && msgs[0].patient_type ? msgs[0].patient_type : 'unknown';
    var totalMsgs = msgs.length;
    var avgLatency = totalMsgs > 0 ? Math.round(msgs.reduce(function(s, m) { return s + (m.response_time_ms || 0); }, 0) / totalMsgs) : 0;
    stats.innerHTML = '<span class="modal-stat-badge teal">' + esc(patientType) + ' patient</span>'
      + '<span class="modal-stat-badge">' + totalMsgs + ' messages</span>'
      + '<span class="modal-stat-badge">' + avgLatency + 'ms avg latency</span>';

    if (msgs.length === 0) {
      thread.innerHTML = '<div class="loading-text">No messages found.</div>';
      return;
    }
    var html = '';
    msgs.forEach(function(m) {
      html += '<div class="thread-q">' + esc(m.question) + '</div>';
      html += '<div class="thread-a">' + esc(m.answer);
      html += '<div class="thread-meta">';
      html += '<span class="badge badge-src">' + esc(m.response_source) + '</span>';
      html += '<span class="badge badge-' + m.confidence + '">' + esc(m.confidence) + '</span>';
      if (m.sentiment) {
        var sCls = m.sentiment === 'positive' ? 'badge-high' : m.sentiment === 'negative' ? 'badge-low' : 'badge-medium';
        html += '<span class="badge ' + sCls + '">' + esc(m.sentiment) + '</span>';
      }
      if (m.response_time_ms !== null) html += '<span class="badge">' + m.response_time_ms + 'ms</span>';
      if (m.max_similarity !== null) html += '<span class="badge">sim: ' + m.max_similarity + '</span>';
      html += '</div>';
      if (fbMap[m.question] !== undefined) {
        var r = fbMap[m.question];
        html += '<div class="thread-fb ' + (r > 0 ? 'positive' : 'negative') + '">' + (r > 0 ? '\\u{1F44D} Helpful' : '\\u{1F44E} Not helpful') + '</div>';
      }
      html += '</div>';
    });
    thread.innerHTML = html;
  } catch(e) {
    console.error('Session load error:', e);
    thread.innerHTML = '<div class="loading-text">Failed to load session.</div>';
  }
}

function closeModal() {
  document.getElementById('modalOverlay').classList.remove('open');
}

document.addEventListener('keydown', function(e) { if (e.key === 'Escape') closeModal(); });

// Initial load — only Overview tab (3 API calls)
switchTab('overview');
</script>
</body>
</html>"""
