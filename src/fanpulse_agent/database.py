import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

from fanpulse_agent.models import Digest, SportsEntity, ToolResult, TraceEntry, UserProfile


class FanPulseDB:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get("FANPULSE_DB_PATH") or "fanpulse.db"

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                create table if not exists users (
                    id integer primary key autoincrement,
                    external_user_id text,
                    name text not null,
                    phone_number text unique,
                    timezone text not null,
                    digest_schedule text not null,
                    whatsapp_consent integer not null default 0,
                    created_at text
                );

                create table if not exists preferences (
                    id integer primary key autoincrement,
                    user_id integer not null unique,
                    sports_json text not null,
                    clarification_choices_json text not null,
                    profile_json text not null,
                    foreign key (user_id) references users(id)
                );

                create table if not exists sports_entities (
                    id integer primary key autoincrement,
                    user_id integer not null,
                    name text not null,
                    entity_type text not null,
                    sport text not null,
                    source_text text,
                    confidence real,
                    needs_clarification integer not null default 0,
                    clarification_prompt text,
                    league text,
                    external_id text,
                    payload_json text not null,
                    foreign key (user_id) references users(id)
                );

                create table if not exists digest_history (
                    id integer primary key autoincrement,
                    user_id integer not null,
                    title text,
                    generated_at text,
                    summary text,
                    payload_json text not null,
                    foreign key (user_id) references users(id)
                );

                create table if not exists tool_runs (
                    id integer primary key autoincrement,
                    user_id integer not null,
                    tool_name text not null,
                    success integer not null,
                    data_json text,
                    source_url text,
                    error text,
                    confidence real,
                    mock integer not null default 0,
                    payload_json text not null,
                    created_at text default current_timestamp,
                    foreign key (user_id) references users(id)
                );

                create table if not exists agent_trace (
                    id integer primary key autoincrement,
                    user_id integer not null,
                    step text not null,
                    message text not null,
                    timestamp text not null,
                    tool_name text,
                    metadata_json text not null,
                    payload_json text not null,
                    foreign key (user_id) references users(id)
                );
                """
            )

    def save_user_preferences(self, profile: UserProfile) -> int:
        self.initialize()
        with self._connect() as connection:
            existing_id = self._find_user_id(connection, profile)
            if existing_id is None:
                cursor = connection.execute(
                    """
                    insert into users (
                        external_user_id, name, phone_number, timezone,
                        digest_schedule, whatsapp_consent, created_at
                    )
                    values (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        profile.user_id,
                        profile.name,
                        profile.phone_number,
                        profile.timezone,
                        profile.digest_schedule,
                        int(profile.whatsapp_consent),
                        profile.created_at,
                    ),
                )
                user_id = int(cursor.lastrowid)
            else:
                user_id = existing_id
                connection.execute(
                    """
                    update users
                    set external_user_id = ?, name = ?, phone_number = ?, timezone = ?,
                        digest_schedule = ?, whatsapp_consent = ?, created_at = ?
                    where id = ?
                    """,
                    (
                        profile.user_id,
                        profile.name,
                        profile.phone_number,
                        profile.timezone,
                        profile.digest_schedule,
                        int(profile.whatsapp_consent),
                        profile.created_at,
                        user_id,
                    ),
                )

            connection.execute(
                """
                insert into preferences (
                    user_id, sports_json, clarification_choices_json, profile_json
                )
                values (?, ?, ?, ?)
                on conflict(user_id) do update set
                    sports_json = excluded.sports_json,
                    clarification_choices_json = excluded.clarification_choices_json,
                    profile_json = excluded.profile_json
                """,
                (
                    user_id,
                    self._to_json(profile.sports),
                    self._to_json(profile.clarification_choices),
                    self._to_json(profile),
                ),
            )

            connection.execute("delete from sports_entities where user_id = ?", (user_id,))
            for entity in [*profile.teams, *profile.athletes]:
                connection.execute(
                    """
                    insert into sports_entities (
                        user_id, name, entity_type, sport, source_text, confidence,
                        needs_clarification, clarification_prompt, league, external_id,
                        payload_json
                    )
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        entity.name,
                        entity.entity_type,
                        entity.sport,
                        entity.source_text,
                        entity.confidence,
                        int(entity.needs_clarification),
                        entity.clarification_prompt,
                        entity.league,
                        entity.external_id,
                        self._to_json(entity),
                    ),
                )
            return user_id

    def log_tool_run(self, user_id: int, result: ToolResult) -> int:
        self.initialize()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                insert into tool_runs (
                    user_id, tool_name, success, data_json, source_url, error,
                    confidence, mock, payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    result.tool_name,
                    int(result.success),
                    self._to_json(result.data),
                    result.source_url,
                    result.error,
                    result.confidence,
                    int(result.mock),
                    self._to_json(result),
                ),
            )
            return int(cursor.lastrowid)

    def log_trace(self, user_id: int, entry: TraceEntry) -> int:
        self.initialize()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                insert into agent_trace (
                    user_id, step, message, timestamp, tool_name, metadata_json,
                    payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    entry.step,
                    entry.message,
                    entry.timestamp,
                    entry.tool_name,
                    self._to_json(entry.metadata),
                    self._to_json(entry),
                ),
            )
            return int(cursor.lastrowid)

    def save_digest_history(self, user_id: int, digest: Digest) -> int:
        self.initialize()
        payload = self._as_payload(digest)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                insert into digest_history (
                    user_id, title, generated_at, summary, payload_json
                )
                values (?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    payload.get("title"),
                    payload.get("generated_at"),
                    payload.get("summary"),
                    self._to_json(payload),
                ),
            )
            return int(cursor.lastrowid)

    def load_enrolled_users(self) -> List[UserProfile]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                select users.id, users.external_user_id, users.name, users.phone_number,
                       users.timezone, users.digest_schedule, users.whatsapp_consent,
                       users.created_at, preferences.sports_json,
                       preferences.clarification_choices_json
                from users
                left join preferences on preferences.user_id = users.id
                order by users.id
                """
            ).fetchall()
            return [self._profile_from_row(connection, row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _find_user_id(
        self, connection: sqlite3.Connection, profile: UserProfile
    ) -> Optional[int]:
        if profile.phone_number:
            row = connection.execute(
                "select id from users where phone_number = ?", (profile.phone_number,)
            ).fetchone()
            if row:
                return int(row[0])
        if profile.user_id:
            row = connection.execute(
                "select id from users where external_user_id = ?", (profile.user_id,)
            ).fetchone()
            if row:
                return int(row[0])
        return None

    def _profile_from_row(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> UserProfile:
        user_id = int(row[0])
        teams, athletes = self._load_entities(connection, user_id)
        return UserProfile(
            user_id=str(row[1] or user_id),
            name=row[2],
            phone_number=row[3],
            timezone=row[4],
            digest_schedule=row[5],
            whatsapp_consent=bool(row[6]),
            teams=teams,
            athletes=athletes,
            sports=self._from_json(row[8], []),
            clarification_choices=self._from_json(row[9], {}),
            favorite_teams=teams,
            favorite_sports=self._from_json(row[8], []),
            created_at=row[7],
        )

    def _load_entities(
        self, connection: sqlite3.Connection, user_id: int
    ) -> tuple[List[SportsEntity], List[SportsEntity]]:
        rows = connection.execute(
            """
            select name, entity_type, sport, source_text, confidence,
                   needs_clarification, clarification_prompt, league, external_id
            from sports_entities
            where user_id = ?
            order by id
            """,
            (user_id,),
        ).fetchall()
        teams: List[SportsEntity] = []
        athletes: List[SportsEntity] = []
        for row in rows:
            entity = SportsEntity(
                name=row[0],
                entity_type=row[1],
                sport=row[2],
                source_text=row[3] or "",
                confidence=float(row[4]) if row[4] is not None else 0.9,
                needs_clarification=bool(row[5]),
                clarification_prompt=row[6],
                league=row[7],
                external_id=row[8],
            )
            if entity.entity_type == "athlete":
                athletes.append(entity)
            else:
                teams.append(entity)
        return teams, athletes

    def _to_json(self, value: Any) -> str:
        return json.dumps(self._as_payload(value), sort_keys=True)

    def _as_payload(self, value: Any) -> Any:
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if isinstance(value, list):
            return [self._as_payload(item) for item in value]
        if isinstance(value, tuple):
            return [self._as_payload(item) for item in value]
        if isinstance(value, dict):
            return {key: self._as_payload(item) for key, item in value.items()}
        return value

    def _from_json(self, value: Optional[str], default: Any) -> Any:
        if not value:
            return default
        return json.loads(value)
