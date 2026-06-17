from __future__ import annotations

import sqlite3
import sys
from html import escape
from pathlib import Path
from typing import Any, Iterable

import streamlit as st
import streamlit.components.v1 as components

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fanpulse_agent.agent import AgentResponse, FanPulseAgent
from fanpulse_agent.database import FanPulseDB
from fanpulse_agent.models import Digest, Event, TraceEntry, UserProfile
from fanpulse_agent.ui_state import should_accept_user_message

FANPULSE_PHONE = components.declare_component(
    "fanpulse_phone",
    path=str(Path(__file__).resolve().parent / "components" / "fanpulse_phone"),
)

SAMPLE_ONBOARDING = (
    "I am Mansoor. I follow the Lakers, Real Madrid, India cricket, "
    "Novak Djokovic and Max Verstappen. Send my digest every Friday morning "
    "to +14155550123 on WhatsApp. Use Pacific time."
)

AMBIGUITY_CHOICES = (
    "India men's national cricket team",
    "India women's national cricket team",
    "Indian Premier League cricket",
)


st.set_page_config(page_title="FanPulse AI", page_icon="🏆", layout="wide")


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --fp-bg: #07111f;
            --fp-panel: #0f1b2d;
            --fp-panel-2: #122139;
            --fp-line: #22324b;
            --fp-text: #f3f7ff;
            --fp-muted: #93a4bd;
            --fp-green: #22c55e;
            --fp-blue: #4fc3ff;
            --fp-purple: #8b5cf6;
            --fp-gold: #f59e0b;
        }
        .stApp {
            background:
                radial-gradient(circle at 20% 0%, #183b64, transparent 34%),
                linear-gradient(135deg, #06101e, #0b1020);
            color: var(--fp-text);
        }
        [data-testid="stHeader"] { background: rgba(8, 11, 18, 0); }
        [data-testid="stSidebar"] { background: var(--fp-bg); }
        .block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 1280px; }
        .fp-shell {
            border: 1px solid var(--fp-line);
            background: rgba(255, 255, 255, 0.045);
            border-radius: 20px;
            padding: 1rem;
            box-shadow: 0 32px 90px rgba(0, 0, 0, 0.25);
        }
        .fp-logo {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            color: var(--fp-text);
            font-size: 1.35rem;
            font-weight: 900;
            margin-bottom: 2.8rem;
        }
        .fp-mark {
            width: 44px;
            height: 44px;
            border-radius: 16px;
            display: inline-grid;
            place-items: center;
            background: linear-gradient(135deg, var(--fp-blue), var(--fp-purple));
            box-shadow: 0 14px 44px rgba(79, 195, 255, 0.20);
        }
        .fp-kicker {
            color: var(--fp-blue);
            font-size: 0.76rem;
            font-weight: 900;
            letter-spacing: 0;
            text-transform: uppercase;
        }
        .fp-title {
            color: #f8fafc;
            font-size: 3.55rem;
            font-weight: 950;
            line-height: 0.98;
            margin: 0.5rem 0 1.1rem;
        }
        .fp-subtle { color: #c5d3e7; font-size: 1.05rem; line-height: 1.6; }
        .fp-mini-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.75rem;
            margin-top: 1.6rem;
        }
        .fp-mini-card {
            border: 1px solid var(--fp-line);
            background: rgba(255, 255, 255, 0.045);
            border-radius: 20px;
            padding: 1rem;
        }
        .fp-mini-card b { display: block; margin-bottom: 0.45rem; color: #fff; }
        .fp-mini-card span { color: var(--fp-muted); font-size: 0.82rem; line-height: 1.45; }
        .fp-card {
            border: 1px solid var(--fp-line);
            background: rgba(255, 255, 255, 0.04);
            border-radius: 20px;
            padding: 0.95rem;
            margin-bottom: 0.8rem;
        }
        .fp-card h3 {
            color: #f8fafc;
            font-size: 1rem;
            margin: 0 0 0.45rem;
        }
        .fp-label { color: var(--fp-muted); font-size: 0.78rem; text-transform: uppercase; font-weight: 700; }
        .fp-metric {
            color: #f8fafc;
            font-size: 1.35rem;
            font-weight: 800;
            line-height: 1.2;
        }
        .fp-pill {
            display: inline-block;
            border: 1px solid rgba(56, 189, 248, 0.32);
            background: rgba(56, 189, 248, 0.10);
            border-radius: 999px;
            color: #dff6ff;
            font-size: 0.78rem;
            padding: 0.2rem 0.55rem;
            margin: 0.12rem 0.18rem 0.12rem 0;
        }
        .fp-phone {
            background: linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.03));
            border: 1px solid var(--fp-line);
            border-radius: 36px;
            padding: 16px;
            box-shadow: 0 32px 90px rgba(0,0,0,.32);
            max-width: 470px;
            margin: 0 auto;
        }
        .fp-phone-topbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #0b1729;
            border: 1px solid #1e2f49;
            border-bottom: 0;
            border-radius: 26px 26px 0 0;
            padding: 16px 18px;
        }
        .fp-agent-profile { display: flex; gap: 11px; align-items: center; }
        .fp-avatar {
            width: 39px;
            height: 39px;
            border-radius: 14px;
            display: grid;
            place-items: center;
            background: linear-gradient(135deg, var(--fp-blue), var(--fp-green));
        }
        .fp-phone-body {
            background: #071321;
            border: 1px solid #1e2f49;
            border-top: 0;
            border-radius: 0 0 26px 26px;
            padding: 18px;
            min-height: 690px;
            display: flex;
            flex-direction: column;
        }
        .fp-chat-content {
            overflow-y: auto;
            padding: 0 2px 0.75rem 0;
            scrollbar-color: #264363 #071321;
        }
        .fp-msg {
            max-width: 86%;
            padding: 12px 14px;
            border-radius: 17px;
            margin: 10px 0;
            line-height: 1.45;
            font-size: 14px;
            color: #f3f7ff !important;
            overflow-wrap: anywhere;
        }
        .fp-msg * {
            color: inherit !important;
        }
        .fp-msg-agent {
            background: #11243d;
            border-bottom-left-radius: 5px;
        }
        .fp-msg-user {
            background: linear-gradient(135deg, var(--fp-blue), var(--fp-purple));
            margin-left: auto;
            border-bottom-right-radius: 5px;
        }
        .fp-event {
            display: grid;
            grid-template-columns: 42px 1fr;
            gap: 12px;
            border: 1px solid var(--fp-line);
            background: #0a1729;
            border-radius: 16px;
            padding: 12px;
        }
        .fp-emoji {
            width: 42px;
            height: 42px;
            display: grid;
            place-items: center;
            border-radius: 14px;
            background: #152948;
            font-size: 1.25rem;
        }
        .fp-event-meta {
            color: var(--fp-muted);
            font-size: 0.82rem;
            margin-top: 0.35rem;
        }
        .fp-source {
            color: #bae6fd;
            font-size: 0.8rem;
            word-break: break-word;
        }
        .fp-source a { color: #8bdcff !important; text-decoration: none; }
        .fp-phone-card {
            border: 1px solid var(--fp-line);
            background: rgba(255, 255, 255, 0.04);
            border-radius: 16px;
            padding: 12px;
            margin: 12px 0;
            color: #f3f7ff;
        }
        .fp-phone-card h3 {
            color: #f8fafc;
            font-size: 1rem;
            margin: 0.25rem 0 0.4rem;
        }
        .fp-pref-row {
            display: grid;
            grid-template-columns: 86px 1fr;
            gap: 10px;
            border-top: 1px solid rgba(255, 255, 255, 0.07);
            padding-top: 10px;
            margin-top: 10px;
        }
        .fp-pref-label {
            color: var(--fp-muted);
            font-size: 0.74rem;
            font-weight: 800;
            text-transform: uppercase;
        }
        .fp-phone-event {
            display: grid;
            grid-template-columns: 42px 1fr;
            gap: 12px;
            border: 1px solid var(--fp-line);
            background: #0a1729;
            border-radius: 14px;
            padding: 12px;
            margin-top: 10px;
        }
        .fp-action-tray {
            border-top: 1px solid rgba(255,255,255,.08);
            padding-top: 12px;
            margin-top: 8px;
        }
        .fp-status-ok { color: var(--fp-green); font-weight: 700; }
        .fp-status-wait { color: var(--fp-gold); font-weight: 700; }
        .stButton > button {
            border-radius: 15px;
            border: 1px solid var(--fp-line);
            background: rgba(255,255,255,.06);
            color: #f8fafc;
            min-height: 2.55rem;
            font-weight: 850;
        }
        .stButton > button:hover {
            border-color: rgba(56, 189, 248, 0.72);
            color: #ffffff;
        }
        [data-testid="stTextInput"] input {
            background: #091a2e !important;
            color: var(--fp-text) !important;
            border-color: var(--fp-line) !important;
            border-radius: 14px !important;
            min-height: 2.75rem;
        }
        [data-testid="stForm"] {
            border: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
            background: transparent !important;
        }
        @media (max-width: 950px) {
            .fp-title { font-size: 2.65rem; }
            .fp-mini-grid { grid-template-columns: 1fr; }
            .fp-phone { max-width: 100%; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def initialize_state() -> None:
    if "db" not in st.session_state:
        st.session_state.db = FanPulseDB()
        st.session_state.db.initialize()
    if "agent" not in st.session_state:
        st.session_state.agent = FanPulseAgent(st.session_state.db)
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Tell me who you follow, how often to update you, and where to send your WhatsApp digest.",
            }
        ]
    if "last_response" not in st.session_state:
        st.session_state.last_response = None
    if "weekly_status" not in st.session_state:
        st.session_state.weekly_status = ""


def set_response(response: AgentResponse) -> None:
    st.session_state.last_response = response
    st.session_state.profile = response.profile
    st.session_state.digest = response.digest
    st.session_state.messages.append({"role": "assistant", "content": response.message})


def submit_user_message(text: str) -> None:
    if not text.strip():
        return
    if not should_accept_user_message(st.session_state.messages, text):
        return
    st.session_state.messages.append({"role": "user", "content": text})
    set_response(st.session_state.agent.handle_user_message(text))


def resolve_ambiguity(choice: str) -> None:
    st.session_state.messages.append({"role": "user", "content": choice})
    set_response(st.session_state.agent.resolve_ambiguity(choice))


def confirm_preferences() -> None:
    set_response(st.session_state.agent.confirm_preferences())


def approve_digest() -> None:
    set_response(st.session_state.agent.approve_and_send_digest())


def request_digest_changes() -> None:
    st.session_state.messages.append({"role": "user", "content": "Ask for changes"})
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": "Tell me what you want changed in this digest and I will update it before sending.",
        }
    )


def run_weekly_job() -> None:
    try:
        from weekly_digest_job import run_weekly_digest_job
    except ModuleNotFoundError as exc:
        if exc.name != "weekly_digest_job":
            raise
        st.session_state.weekly_status = (
            "Scheduled digest job is not installed yet. Task 8 will add weekly_digest_job.py."
        )
        return

    try:
        summary = run_weekly_digest_job(st.session_state.db.db_path)
    except Exception as exc:
        st.session_state.weekly_status = f"Scheduled run did not complete: {exc}"
        return
    st.session_state.weekly_status = (
        f"Scheduled run complete: {summary.get('processed', 0)} processed, "
        f"{summary.get('sent', 0)} sent."
    )


def reset_conversation() -> None:
    db = st.session_state.get("db")
    weekly_status = st.session_state.get("weekly_status", "")
    st.session_state.clear()
    if db is not None:
        st.session_state.db = db
    st.session_state.weekly_status = weekly_status
    initialize_state()


def query_value(name: str) -> str:
    value = st.query_params.get(name, "")
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


def process_phone_commands() -> None:
    prompt = query_value("fanpulse_prompt").strip()
    action = query_value("fanpulse_action").strip()
    choice = query_value("fanpulse_choice").strip()

    handled = False
    if prompt:
        submit_user_message(prompt)
        handled = True
    elif action == "clarify_ambiguity" and choice:
        resolve_ambiguity(choice)
        handled = True
    elif action == "confirm_preferences":
        confirm_preferences()
        handled = True
    elif action == "approve_digest":
        approve_digest()
        handled = True
    elif action == "ask_changes":
        request_digest_changes()
        handled = True

    if handled:
        st.query_params.clear()
        st.rerun()


def process_phone_event(event: dict[str, Any] | None) -> None:
    if not isinstance(event, dict):
        return

    event_id = str(event.get("event_id") or "")
    if not event_id or st.session_state.get("last_phone_event_id") == event_id:
        return

    kind = str(event.get("kind") or "")
    handled = False
    if kind == "prompt":
        submit_user_message(str(event.get("prompt") or ""))
        handled = True
    elif kind == "action":
        action = str(event.get("action") or "")
        choice = str(event.get("choice") or "")
        if action == "clarify_ambiguity" and choice:
            resolve_ambiguity(choice)
            handled = True
        elif action == "confirm_preferences":
            confirm_preferences()
            handled = True
        elif action == "approve_digest":
            approve_digest()
            handled = True
        elif action == "ask_changes":
            request_digest_changes()
            handled = True

    if handled:
        st.session_state.last_phone_event_id = event_id
        st.rerun()


def render_profile(profile: UserProfile | None) -> None:
    if profile is None:
        st.markdown(
            """
            <div class="fp-card">
                <div class="fp-label">Profile</div>
                <div class="fp-subtle">No active fan profile yet.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    teams = [entity.name for entity in profile.teams]
    athletes = [entity.name for entity in profile.athletes]
    leagues = [entity.name for entity in profile.leagues]
    sports = profile.sports or profile.favorite_sports
    consent = "WhatsApp ready" if profile.whatsapp_consent and profile.phone_number else "Needs consent or phone"
    status_class = "fp-status-ok" if profile.whatsapp_consent and profile.phone_number else "fp-status-wait"

    st.markdown(
        f"""
        <div class="fp-card">
            <div class="fp-label">Profile</div>
            <h3>{escape(profile.name)}</h3>
            <div class="{status_class}">{consent}</div>
            <div class="fp-subtle">{escape(profile.digest_schedule)} · {escape(profile.timezone)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_pills("Teams", teams)
    render_pills("Athletes", athletes)
    render_pills("Sports", sports)


def render_pills(label: str, values: Iterable[str]) -> None:
    values = list(values)
    if not values:
        return
    pills = "".join(f'<span class="fp-pill">{escape(value)}</span>' for value in values)
    st.markdown(
        f"""
        <div class="fp-card">
            <div class="fp-label">{escape(label)}</div>
            <div>{pills}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def pills_markup(values: Iterable[str]) -> str:
    return "".join(f'<span class="fp-pill">{escape(value)}</span>' for value in values)


def preference_card_markup(profile: UserProfile | None) -> str:
    if profile is None:
        return ""

    teams = [entity.name for entity in profile.teams]
    athletes = [entity.name for entity in profile.athletes]
    leagues = [entity.name for entity in profile.leagues]
    sports = profile.sports or profile.favorite_sports
    consent = "WhatsApp ready" if profile.whatsapp_consent and profile.phone_number else "Needs consent or phone"
    status_class = "fp-status-ok" if profile.whatsapp_consent and profile.phone_number else "fp-status-wait"
    phone_label = profile.phone_number or "Not provided"

    rows = [
        ("Teams", pills_markup(teams) or '<span class="fp-subtle">None yet</span>'),
        ("Athletes", pills_markup(athletes) or '<span class="fp-subtle">None yet</span>'),
        ("Leagues", pills_markup(leagues) or '<span class="fp-subtle">None yet</span>'),
        ("Sports", pills_markup(sports) or '<span class="fp-subtle">None yet</span>'),
        (
            "Delivery",
            f'<span class="{status_class}">{consent}</span>'
            f'<div class="fp-event-meta">{escape(phone_label)} · {escape(profile.digest_schedule)} · {escape(profile.timezone)}</div>',
        ),
    ]
    rendered_rows = "".join(
        f"""
        <div class="fp-pref-row">
            <div class="fp-pref-label">{escape(label)}</div>
            <div>{value}</div>
        </div>
        """
        for label, value in rows
    )
    return f"""
    <div class="fp-phone-card">
        <div class="fp-label">Preference Confirmation</div>
        <h3>{escape(profile.name)}</h3>
        {rendered_rows}
    </div>
    """


def event_card_markup(event: Event) -> str:
    sport = event.metadata.get("sport", "sport")
    league = event.metadata.get("league", "league")
    confidence = event.confidence
    mock = event.mock
    incomplete = event.incomplete
    source = event.source_url or "mock://fanpulse-agent"
    source_href = escape(source, quote=True)
    source_text = escape(source)
    display_time = event.display_time or event.start_time or "Time TBD"
    opponent = f" · vs {escape(event.opponent)}" if event.opponent else ""
    status_label = "incomplete" if incomplete else "complete"
    mode_label = "mock mode" if mock else "live source"
    return f"""
    <div class="fp-phone-event">
        <div class="fp-emoji">{escape(event.sport_icon)}</div>
        <div>
            <div class="fp-label">{escape(event.entity_name or "FanPulse")}</div>
            <h3>{escape(event.title)}</h3>
            <div class="fp-event-meta">{escape(display_time)}{opponent} · {escape(str(league))} · {escape(str(sport))}</div>
            <div class="fp-event-meta">confidence {confidence:.0%} · {mode_label} · {status_label}</div>
            <div class="fp-source"><a href="{source_href}" target="_blank" rel="noopener noreferrer">{source_text}</a></div>
        </div>
    </div>
    """


def digest_card_markup(digest: Digest | None) -> str:
    if digest is None:
        return ""

    sent_label = "sent" if getattr(digest, "sent", False) else "awaiting approval"
    unresolved_markup = ""
    if digest.unresolved:
        unresolved_markup = f"""
        <div class="fp-pref-row">
            <div class="fp-pref-label">Unresolved</div>
            <div>
                <div class="fp-subtle">No event source confirmed these preferences.</div>
                {pills_markup(digest.unresolved)}
            </div>
        </div>
        """
    events_markup = "".join(event_card_markup(event) for event in digest.events)
    return f"""
    <div class="fp-phone-card">
        <div class="fp-label">Digest Preview</div>
        <h3>{escape(digest.title)}</h3>
        <div class="fp-subtle">{escape(digest.summary or "No summary generated.")}</div>
        <div class="fp-event-meta">{len(digest.events)} items · {sent_label}</div>
        {unresolved_markup}
        {events_markup}
    </div>
    """


def whatsapp_sent_markup(digest: Digest | None) -> str:
    if digest is None or not getattr(digest, "sent", False):
        return ""

    event_lines = "".join(
        f"""
        <div class="wa-event">
            {escape(event.sport_icon or "•")} <b>{escape(event.title)}</b><br>
            <span>{escape(event.display_time or event.start_time or "Time TBD")}</span><br>
            <span>Source: {escape(event.source_url or "mock://fanpulse-agent")}</span>
        </div>
        """
        for event in digest.events[:4]
    )
    if not event_lines:
        event_lines = "<div class=\"wa-event\">No upcoming events were confirmed for this digest.</div>"

    return f"""
    <div class="whatsapp">
        🏆 <b>{escape(digest.title)}</b>
        {event_lines}
        <div class="wa-footer">Reply “update preferences” anytime.</div>
    </div>
    """


def support_cards_for_state(
    profile: UserProfile | None,
    digest: Digest | None,
    response: AgentResponse | None,
) -> list[str]:
    if response is None:
        return []

    cards: list[str] = []
    if response.requires_action == "confirm_preferences":
        cards.append(preference_card_markup(profile))
    elif response.requires_action in {"approve_digest", "collect_contact"}:
        cards.extend([preference_card_markup(profile), digest_card_markup(digest)])
    elif response.requires_action == "complete":
        cards.extend(
            [
                digest_card_markup(digest),
                whatsapp_sent_markup(digest),
            ]
        )
    return [card for card in cards if card]


def render_digest(digest: Digest | None) -> None:
    if digest is None:
        st.markdown(
            """
            <div class="fp-card">
                <div class="fp-label">Digest Preview</div>
                <div class="fp-subtle">Your preview appears after preferences are confirmed.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    sent_label = "sent" if getattr(digest, "sent", False) else "awaiting approval"
    st.markdown(
        f"""
        <div class="fp-card">
            <div class="fp-label">Digest Preview</div>
            <h3>{escape(digest.title)}</h3>
            <div class="fp-subtle">{escape(digest.summary or "No summary generated.")}</div>
            <div class="fp-event-meta">{len(digest.events)} items · {sent_label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if digest.unresolved:
        unresolved_items = "".join(
            f'<span class="fp-pill">{escape(item)}</span>' for item in digest.unresolved
        )
        st.markdown(
            f"""
            <div class="fp-card">
                <div class="fp-label">Unresolved</div>
                <div class="fp-subtle">No event source confirmed these preferences.</div>
                <div>{unresolved_items}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    for event in digest.events:
        render_event_card(event)


def render_event_card(event: Event) -> None:
    sport = event.metadata.get("sport", "sport")
    league = event.metadata.get("league", "league")
    confidence = event.confidence
    mock = event.mock
    incomplete = event.incomplete
    source = event.source_url or "mock://fanpulse-agent"
    source_href = escape(source, quote=True)
    source_text = escape(source)
    display_time = event.display_time or event.start_time or "Time TBD"
    opponent = f" · vs {escape(event.opponent)}" if event.opponent else ""
    status_label = "incomplete" if incomplete else "complete"
    mode_label = "mock mode" if mock else "live source"
    st.markdown(
        f"""
        <div class="fp-card fp-event">
            <div class="fp-label">{escape(event.sport_icon)} {escape(event.entity_name or "FanPulse")}</div>
            <h3>{escape(event.title)}</h3>
            <div class="fp-event-meta">{escape(display_time)}{opponent} · {escape(str(league))} · {escape(str(sport))}</div>
            <div class="fp-event-meta">confidence {confidence:.0%} · {mode_label} · {status_label}</div>
            <div class="fp-source"><a href="{source_href}" target="_blank" rel="noopener noreferrer">{source_text}</a></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_chat_transcript(messages: list[dict[str, str]]) -> None:
    rendered = []
    for message in messages:
        role = message.get("role", "assistant")
        bubble_class = "fp-msg-user" if role == "user" else "fp-msg-agent"
        rendered.append(
            f'<div class="fp-msg {bubble_class}">{escape(message.get("content", ""))}</div>'
        )
    st.markdown(
        f'<div class="fp-chat-content">{"".join(rendered)}</div>',
        unsafe_allow_html=True,
    )


def render_phone_scroll(
    messages: list[dict[str, str]],
    profile: UserProfile | None,
    digest: Digest | None,
) -> None:
    with st.container(height=560, border=False):
        for message in messages:
            role = message.get("role", "assistant")
            bubble_class = "fp-msg-user" if role == "user" else "fp-msg-agent"
            st.markdown(
                f'<div class="fp-msg {bubble_class}">{escape(message.get("content", ""))}</div>',
                unsafe_allow_html=True,
            )
        if profile is not None:
            st.markdown(preference_card_markup(profile), unsafe_allow_html=True)
        if digest is not None:
            st.markdown(digest_card_markup(digest), unsafe_allow_html=True)


def render_phone_input() -> None:
    with st.form("fanpulse-message-form", clear_on_submit=True, border=False):
        input_col, send_col = st.columns([4, 1], vertical_alignment="bottom")
        with input_col:
            prompt = st.text_input(
                "Message",
                placeholder="Tell FanPulse who you follow...",
                label_visibility="collapsed",
            )
        with send_col:
            submitted = st.form_submit_button("Send", width="stretch")
    if submitted and prompt:
        submit_user_message(prompt)
        st.rerun()


def js_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "")


def action_button(label: str, action: str, choice: str = "") -> str:
    choice_attr = f' data-fp-choice="{escape(choice, quote=True)}"' if choice else ""
    return (
        f'<button class="fp-action-button" type="button" '
        f'data-fp-action="{escape(action, quote=True)}"{choice_attr}>{escape(label)}</button>'
    )


def phone_html(
    messages: list[dict[str, str]],
    profile: UserProfile | None,
    digest: Digest | None,
    response: AgentResponse | None,
    status_text: str,
) -> str:
    timeline = []
    last_assistant_index = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if messages[index].get("role", "assistant") == "assistant"
        ),
        None,
    )
    support_cards = support_cards_for_state(profile, digest, response)
    for source_index, message in enumerate(messages):
        if source_index == last_assistant_index:
            timeline.extend(support_cards)
        role = message.get("role", "assistant")
        bubble_class = "user" if role == "user" else "agent"
        timeline.append(
            f'<div class="msg {bubble_class}">{escape(message.get("content", ""))}</div>'
        )

    actions = ""
    if response is not None:
        if response.requires_action == "clarify_ambiguity":
            choices = "".join(
                action_button(choice, "clarify_ambiguity", choice) for choice in AMBIGUITY_CHOICES
            )
            actions = f'<div class="action-note">Choose the India Cricket meaning to continue.</div><div class="actions">{choices}</div>'
        elif response.requires_action == "confirm_preferences":
            actions = f'<div class="actions">{action_button("Confirm Preferences", "confirm_preferences")}</div>'
        elif response.requires_action == "approve_digest":
            actions = (
                f'<div class="actions">'
                f'{action_button("Approve And Send Digest", "approve_digest")}'
                f'{action_button("Ask For Changes", "ask_changes")}'
                f'</div>'
            )

    return f"""
      <style>
        :root {{
          --bg: #071321;
          --line: #22324b;
          --muted: #93a4bd;
          --text: #f3f7ff;
          --blue: #4fc3ff;
          --purple: #8b5cf6;
          --green: #22c55e;
          --gold: #f59e0b;
        }}
        * {{ box-sizing: border-box; }}
        body {{
          margin: 0;
          background: transparent;
          color: var(--text);
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }}
        .phone {{
          max-width: 470px;
          margin: 0 auto;
          background: linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.03));
          border: 1px solid var(--line);
          border-radius: 36px;
          padding: 16px;
          box-shadow: 0 32px 90px rgba(0,0,0,.32);
        }}
        .inner {{
          height: 760px;
          background: var(--bg);
          border: 1px solid #1e2f49;
          border-radius: 26px;
          overflow: hidden;
          display: flex;
          flex-direction: column;
        }}
        .topbar {{
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: #0b1729;
          padding: 16px 18px;
          border-bottom: 1px solid #1e2f49;
        }}
        .agent-profile {{ display: flex; gap: 11px; align-items: center; min-width: 0; }}
        .avatar {{
          width: 39px;
          height: 39px;
          border-radius: 14px;
          display: grid;
          place-items: center;
          background: linear-gradient(135deg, var(--blue), var(--green));
          flex: 0 0 auto;
        }}
        .agent-name {{ font-weight: 900; color: #fff; }}
        .agent-status, .wa {{ font-size: 12px; color: var(--muted); }}
        .content {{
          flex: 1;
          overflow-y: auto;
          padding: 18px;
          scrollbar-color: #264363 var(--bg);
        }}
        .msg {{
          max-width: 86%;
          padding: 12px 14px;
          border-radius: 17px;
          margin: 10px 0;
          line-height: 1.45;
          font-size: 14px;
          color: var(--text);
          overflow-wrap: anywhere;
        }}
        .agent {{
          background: #11243d;
          border-bottom-left-radius: 5px;
        }}
        .user {{
          background: linear-gradient(135deg, var(--blue), var(--purple));
          margin-left: auto;
          border-bottom-right-radius: 5px;
        }}
        .fp-phone-card {{
          border: 1px solid var(--line);
          background: rgba(255, 255, 255, 0.04);
          border-radius: 16px;
          padding: 12px;
          margin: 12px 0;
          color: var(--text);
        }}
        .fp-phone-card h3,
        .fp-phone-event h3 {{
          color: #f8fafc;
          font-size: 1rem;
          margin: 0.25rem 0 0.4rem;
        }}
        .fp-label {{
          color: var(--muted);
          font-size: 0.74rem;
          font-weight: 800;
          text-transform: uppercase;
        }}
        .fp-subtle {{ color: #c5d3e7; font-size: .9rem; line-height: 1.45; }}
        .fp-pill {{
          display: inline-block;
          border: 1px solid rgba(56, 189, 248, 0.32);
          background: rgba(56, 189, 248, 0.10);
          border-radius: 999px;
          color: #dff6ff;
          font-size: 0.78rem;
          padding: 0.2rem 0.55rem;
          margin: 0.12rem 0.18rem 0.12rem 0;
        }}
        .fp-pref-row {{
          display: grid;
          grid-template-columns: 86px 1fr;
          gap: 10px;
          border-top: 1px solid rgba(255, 255, 255, 0.07);
          padding-top: 10px;
          margin-top: 10px;
        }}
        .fp-pref-label {{
          color: var(--muted);
          font-size: 0.74rem;
          font-weight: 800;
          text-transform: uppercase;
        }}
        .fp-event-meta {{
          color: var(--muted);
          font-size: 0.82rem;
          margin-top: 0.35rem;
        }}
        .fp-status-ok {{ color: var(--green); font-weight: 700; }}
        .fp-status-wait {{ color: var(--gold); font-weight: 700; }}
        .fp-phone-event {{
          display: grid;
          grid-template-columns: 42px 1fr;
          gap: 12px;
          border: 1px solid var(--line);
          background: #0a1729;
          border-radius: 14px;
          padding: 12px;
          margin-top: 10px;
        }}
        .fp-emoji {{
          width: 42px;
          height: 42px;
          display: grid;
          place-items: center;
          border-radius: 14px;
          background: #152948;
          font-size: 1.25rem;
        }}
        .fp-source {{
          color: #bae6fd;
          font-size: 0.8rem;
          word-break: break-word;
        }}
        .fp-source a {{ color: #8bdcff; text-decoration: none; }}
        .action-note {{
          color: var(--muted);
          font-size: 12px;
          margin: 12px 0 8px;
        }}
        .actions {{
          display: grid;
          gap: 8px;
          margin: 12px 0 0;
        }}
        .fp-action-button {{
          width: 100%;
          min-height: 42px;
          border-radius: 15px;
          border: 1px solid var(--line);
          background: rgba(255,255,255,.06);
          color: #f8fafc;
          font-weight: 850;
          cursor: pointer;
        }}
        .whatsapp {{
          background: #dcf8c6;
          color: #122018;
          border-radius: 17px 17px 5px 17px;
          padding: 13px 14px;
          line-height: 1.45;
          margin: 12px 0 10px auto;
          max-width: 92%;
          font-size: 14px;
          box-shadow: 0 12px 24px rgba(34, 197, 94, .12);
        }}
        .whatsapp b {{
          color: #122018;
        }}
        .wa-event {{
          margin-top: 12px;
        }}
        .wa-event span,
        .wa-footer {{
          color: #35513f;
          font-size: 13px;
        }}
        .wa-footer {{
          margin-top: 12px;
        }}
        .inputbar {{
          display: grid;
          grid-template-columns: 1fr 76px;
          gap: 10px;
          padding: 14px;
          border-top: 1px solid rgba(255,255,255,.08);
          background: #071321;
        }}
        .inputbar input {{
          min-width: 0;
          min-height: 44px;
          border-radius: 15px;
          border: 1px solid var(--line);
          background: #091a2e;
          color: var(--text);
          padding: 0 13px;
          font-size: 14px;
          outline: none;
        }}
        .inputbar button {{
          min-height: 44px;
          border-radius: 15px;
          border: 0;
          background: linear-gradient(135deg, var(--blue), var(--purple));
          color: white;
          font-weight: 900;
          cursor: pointer;
        }}
      </style>
      <div class="phone">
        <div class="inner">
          <div class="topbar">
            <div class="agent-profile">
              <div class="avatar">🤖</div>
              <div>
                <div class="agent-name">FanPulse Agent</div>
                <div class="agent-status">{escape(status_text)}</div>
              </div>
            </div>
            <div class="wa">WhatsApp-ready</div>
          </div>
          <div class="content" id="content">
            {''.join(timeline)}
            {actions}
          </div>
          <form class="inputbar" data-fp-form>
            <input data-fp-input autocomplete="off" placeholder="Tell FanPulse who you follow..." />
            <button type="submit">Send</button>
          </form>
        </div>
      </div>
    """


def render_actions(response: AgentResponse | None) -> None:
    if response is None:
        return

    if response.requires_action == "clarify_ambiguity":
        st.caption("Choose the India Cricket meaning to continue.")
        columns = st.columns(len(AMBIGUITY_CHOICES))
        for column, choice in zip(columns, AMBIGUITY_CHOICES):
            if column.button(choice, width="stretch"):
                resolve_ambiguity(choice)
                st.rerun()

    if response.requires_action == "confirm_preferences":
        if st.button("Confirm Preferences", width="stretch"):
            confirm_preferences()
            st.rerun()

    if response.requires_action == "approve_digest":
        if st.button("Approve And Send Digest", width="stretch"):
            approve_digest()
            st.rerun()


def render_debug(response: AgentResponse | None) -> None:
    with st.expander("Agent Trace / Debug View", expanded=False):
        st.caption("Mock mode is on by default. Tool names use MCP-style provider prefixes.")
        trace = list(response.trace if response else st.session_state.agent.trace)
        if trace:
            for entry in trace:
                render_trace_entry(entry)
        else:
            st.info("No trace entries yet.")

        recent_runs = load_recent_tool_runs(st.session_state.db)
        if recent_runs:
            st.markdown("Recent tool runs")
            st.dataframe(recent_runs, width="stretch", hide_index=True)


def render_trace_entry(entry: TraceEntry) -> None:
    label = entry.tool_name or entry.step
    st.markdown(f"**{label}** · {entry.message}")
    if entry.metadata:
        st.json(entry.metadata)


def load_recent_tool_runs(db: FanPulseDB) -> list[dict[str, Any]]:
    try:
        with sqlite3.connect(db.db_path) as connection:
            rows = connection.execute(
                """
                select tool_name, success, confidence, mock, created_at
                from tool_runs
                order by id desc
                limit 10
                """
            ).fetchall()
    except sqlite3.Error:
        return []
    return [
        {
            "tool": row[0],
            "success": bool(row[1]),
            "confidence": row[2],
            "mock": bool(row[3]),
            "created_at": row[4],
        }
        for row in rows
    ]


apply_styles()
initialize_state()
process_phone_commands()

last_response = st.session_state.last_response
profile = getattr(last_response, "profile", None) or st.session_state.get("profile")
digest = getattr(last_response, "digest", None) or st.session_state.get("digest")

left, right = st.columns([1.05, 0.95], gap="large")

with left:
    st.markdown(
        """
        <div class="fp-logo"><span class="fp-mark">🏆</span><span>FanPulse</span></div>
        <section class="fp-hero">
            <div class="fp-kicker">FanPulse AI</div>
            <div class="fp-title">Tell it who you follow. It handles the rest.</div>
            <div class="fp-subtle">FanPulse asks for your favorite teams and athletes in plain English, finds the next events, adds source links, and sends a clean recurring WhatsApp digest after approval.</div>
            <div class="fp-mini-grid">
                <div class="fp-mini-card"><b>Conversational</b><span>No long forms. Users can describe teams, athletes, leagues, and delivery preferences in one message.</span></div>
                <div class="fp-mini-card"><b>Agentic</b><span>The agent chooses tools, resolves ambiguity, retries failures, and asks for help when confidence is low.</span></div>
                <div class="fp-mini-card"><b>Safe</b><span>WhatsApp opt-in, first-send approval, source links, and hidden trace logs are built in.</span></div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.write("")
    if st.button("Use Sample Onboarding", width="stretch"):
        submit_user_message(SAMPLE_ONBOARDING)
        st.rerun()
    if st.button("Start Fresh", width="stretch"):
        reset_conversation()
        st.rerun()
    if st.button("Run Scheduled Digest", width="stretch"):
        run_weekly_job()
        st.rerun()
    if st.session_state.weekly_status:
        st.info(st.session_state.weekly_status)

    status_text = "Ready"
    if last_response is not None:
        status_text = last_response.requires_action.replace("_", " ").title()
    st.markdown(
        f"""
        <div class="fp-card">
            <div class="fp-label">Agent Status</div>
            <div class="fp-metric">{escape(status_text)}</div>
            <div class="fp-subtle">Database: {escape(str(st.session_state.db.db_path))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_debug(last_response)

with right:
    phone_event = FANPULSE_PHONE(
        markup=phone_html(st.session_state.messages, profile, digest, last_response, status_text),
        default=None,
        key="fanpulse-phone",
    )
    process_phone_event(phone_event)
