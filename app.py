from __future__ import annotations

import sqlite3
import sys
from html import escape
from pathlib import Path
from typing import Any, Iterable

import streamlit as st

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fanpulse_agent.agent import AgentResponse, FanPulseAgent
from fanpulse_agent.database import FanPulseDB
from fanpulse_agent.models import Digest, Event, TraceEntry, UserProfile


SAMPLE_ONBOARDING = (
    "I am Mansoor. I follow the Lakers, Real Madrid, India cricket, "
    "Novak Djokovic and Max Verstappen. Send my digest every Friday morning "
    "to +14155550123 on WhatsApp."
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
        [data-testid="stChatMessage"] {
            max-width: 86%;
            border: 0;
            border-radius: 17px;
            background: #11243d;
            margin: 0.6rem 0;
            padding: 0.25rem 0.4rem;
        }
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
            margin-left: auto;
            background: linear-gradient(135deg, var(--fp-blue), var(--fp-purple));
        }
        @media (max-width: 950px) {
            .fp-title { font-size: 2.65rem; }
            .fp-mini-grid { grid-template-columns: 1fr; }
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
                "content": "Tell me who you follow and where to send your weekly WhatsApp digest.",
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
    st.session_state.messages.append({"role": "user", "content": text})
    set_response(st.session_state.agent.handle_user_message(text))


def resolve_ambiguity(choice: str) -> None:
    st.session_state.messages.append({"role": "user", "content": choice})
    set_response(st.session_state.agent.resolve_ambiguity(choice))


def confirm_preferences() -> None:
    set_response(st.session_state.agent.confirm_preferences())


def approve_digest() -> None:
    set_response(st.session_state.agent.approve_and_send_digest())


def run_weekly_job() -> None:
    try:
        from weekly_digest_job import run_weekly_digest_job
    except ModuleNotFoundError as exc:
        if exc.name != "weekly_digest_job":
            raise
        st.session_state.weekly_status = (
            "Weekly job is not installed yet. Task 8 will add weekly_digest_job.py."
        )
        return

    try:
        summary = run_weekly_digest_job(st.session_state.db.db_path)
    except Exception as exc:
        st.session_state.weekly_status = f"Weekly run did not complete: {exc}"
        return
    st.session_state.weekly_status = (
        f"Weekly run complete: {summary.get('processed', 0)} processed, "
        f"{summary.get('sent', 0)} sent."
    )


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


def render_actions(response: AgentResponse | None) -> None:
    if response is None:
        return

    if response.requires_action == "clarify_ambiguity":
        st.caption("Choose the India Cricket meaning to continue.")
        columns = st.columns(len(AMBIGUITY_CHOICES))
        for column, choice in zip(columns, AMBIGUITY_CHOICES):
            if column.button(choice, use_container_width=True):
                resolve_ambiguity(choice)
                st.rerun()

    if response.requires_action == "confirm_preferences":
        if st.button("Confirm Preferences", use_container_width=True):
            confirm_preferences()
            st.rerun()

    if response.requires_action == "approve_digest":
        if st.button("Approve And Send Digest", use_container_width=True):
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
            st.dataframe(recent_runs, use_container_width=True, hide_index=True)


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

last_response = st.session_state.last_response
profile = getattr(last_response, "profile", None) or st.session_state.get("profile")
digest = getattr(last_response, "digest", None) or st.session_state.get("digest")

left, right = st.columns([0.92, 1.55], gap="large")

with left:
    st.markdown(
        """
        <div class="fp-logo"><span class="fp-mark">🏆</span><span>FanPulse</span></div>
        <section class="fp-hero">
            <div class="fp-kicker">FanPulse AI</div>
            <div class="fp-title">Tell it who you follow. It handles the rest.</div>
            <div class="fp-subtle">FanPulse asks for your favorite teams and athletes in plain English, finds the next events, adds source links, and sends a clean weekly WhatsApp digest after approval.</div>
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
    if st.button("Use Sample Onboarding", use_container_width=True):
        submit_user_message(SAMPLE_ONBOARDING)
        st.rerun()
    if st.button("Run Weekly Digest", use_container_width=True):
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
    render_profile(profile)

with right:
    st.markdown(
        f"""
        <div class="fp-phone">
        <div class="fp-phone-topbar">
            <div class="fp-agent-profile">
                <div class="fp-avatar">🤖</div>
                <div>
                    <div style="font-weight:900;color:#fff;">FanPulse Agent</div>
                    <div style="font-size:12px;color:#93a4bd;">{escape(status_text)}</div>
                </div>
            </div>
            <div style="font-size:12px;color:#93a4bd;">WhatsApp-ready</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="fp-phone-body">', unsafe_allow_html=True)
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    render_actions(last_response)
    prompt = st.chat_input("Tell FanPulse who you follow...")
    if prompt:
        submit_user_message(prompt)
        st.rerun()
    st.markdown("</div></div>", unsafe_allow_html=True)

    st.write("")
    render_digest(digest)
    render_debug(last_response)
