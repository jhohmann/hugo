"""Shared presentation contract and in-memory fixtures for the timeline."""

from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TimelinePoint(BaseModel):
    id: str
    thread_id: str
    layer: Literal["activity", "planning", "deadline", "idea"]
    title: str
    summary: str
    start: date | datetime | None = None
    end: date | datetime | None = None
    precision: Literal["exact", "approximate", "unknown"] = "unknown"
    origin: Literal["user", "calendar", "hugo", "unknown"] = "unknown"
    commitment: Literal["confirmed", "planned", "suggested", "unknown"] = "unknown"
    time_kind: Literal["recorded", "scheduled", "deadline", "review"]
    source_label: str | None = None
    source_url: str | None = None
    user_activity: bool = False

    @model_validator(mode="after")
    def validate_semantics(self):
        for value in (self.start, self.end):
            if isinstance(value, datetime) and value.utcoffset() is None:
                raise ValueError("Zeitstempel benötigen eine Zeitzone.")
        if self.end is not None:
            if self.start is None or type(self.start) is not type(self.end):
                raise ValueError("Zeiträume benötigen gleichartige Anfangs- und Endwerte.")
            if self.end < self.start:
                raise ValueError("Das Ende darf nicht vor dem Anfang liegen.")
        if self.start is None and self.precision != "unknown":
            raise ValueError("Ohne Datum ist die Genauigkeit unbekannt.")
        if self.layer == "idea" and self.commitment != "suggested":
            raise ValueError("Hugos Ideen müssen als Vorschlag gekennzeichnet sein.")
        if self.user_activity and not (self.layer == "activity" and self.origin == "user"):
            raise ValueError("Nur belegte Nutzeraktivität zählt als Nutzeraktivität.")
        if self.source_url is not None and not (
            (self.source_url.startswith("/") and not self.source_url.startswith("//") and "\\" not in self.source_url)
            or self.source_url.startswith("https://")
        ):
            raise ValueError("Quellverweise müssen intern oder HTTPS-Links sein.")
        return self


class TimelineThread(BaseModel):
    id: str
    title: str
    status: Literal["proposed", "active", "waiting", "completed", "archived"]
    tags: list[Literal["arbeit", "privat"]] = Field(default_factory=list)
    created_on: date
    last_user_activity: date | None = None


class TimelineData(BaseModel):
    demo: bool
    timezone: Literal["Europe/Berlin"] = "Europe/Berlin"
    today: date
    threads: list[TimelineThread] = Field(default_factory=list)
    points: list[TimelinePoint] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self):
        ids = {thread.id for thread in self.threads}
        if len(ids) != len(self.threads) or len({point.id for point in self.points}) != len(self.points):
            raise ValueError("IDs müssen eindeutig sein.")
        if any(point.thread_id not in ids for point in self.points):
            raise ValueError("Jeder Punkt benötigt einen vorhandenen Handlungsstrang.")
        return self


def demo_timeline(today: date, *, large: bool = False) -> TimelineData:
    """Fixtures never touch storage and contain no links to real records."""
    threads = [
        TimelineThread(id="demo-travel", title="Reiseplanung", status="active", tags=["privat"],
                       created_on=today - timedelta(days=730), last_user_activity=today - timedelta(days=90)),
        TimelineThread(id="demo-project", title="Projekt mit einem längeren Titel und ausstehender Rückmeldung", status="waiting",
                       tags=["arbeit"], created_on=today - timedelta(days=35), last_user_activity=today - timedelta(days=7)),
        TimelineThread(id="demo-done", title="Werkstattbesuch", status="completed", tags=["privat"],
                       created_on=today - timedelta(days=80), last_user_activity=today - timedelta(days=10)),
    ]
    points = []
    for thread in threads:
        points.append(TimelinePoint(
            id=thread.id + "-created", thread_id=thread.id, layer="activity", title="Vorhaben angelegt",
            summary="Fiktiver Beginn des Handlungsstrangs.", start=thread.created_on, precision="exact", time_kind="recorded",
        ))
        points.append(TimelinePoint(
            id=thread.id + "-message", thread_id=thread.id, layer="activity", title="Rückmeldung im Gespräch",
            summary="Fiktiver Nachrichtenauszug zur weiteren Planung.", start=thread.last_user_activity,
            precision="exact", origin="user", time_kind="recorded", user_activity=True,
        ))
    for i, (layer, offset, title, origin, commitment) in enumerate([
        ("planning", 40, "Ungefährer Reisezeitraum", "unknown", "planned"),
        ("deadline", 20, "Buchungsfrist", "user", "confirmed"),
        ("idea", 10, "Verbindungen vergleichen", "hugo", "suggested"),
        ("planning", 7, "Bestätigtes Planungsgespräch", "calendar", "confirmed"),
    ]):
        points.append(TimelinePoint(
            id=f"demo-future-{i}", thread_id="demo-travel", layer=layer, title=title,
            summary="Beispieldaten, kein tatsächlicher Termin.", start=today + timedelta(days=offset),
            end=today + timedelta(days=offset + 10) if i == 0 else None,
            precision="approximate" if i == 0 else "exact", origin=origin, commitment=commitment,
            time_kind="deadline" if layer == "deadline" else "scheduled",
        ))
    points.append(TimelinePoint(
        id="demo-undated", thread_id="demo-project", layer="idea", title="Alternativen prüfen",
        summary="Vorschlag ohne festgelegtes Datum.", origin="hugo", commitment="suggested", time_kind="scheduled",
    ))
    for i in range(8):
        points.append(TimelinePoint(
            id=f"demo-dense-{i}", thread_id="demo-project", layer="activity",
            title=f"Abstimmung {i + 1}", summary="Fiktive Rückmeldung zur Projektvorbereitung.",
            start=today - timedelta(days=14 - i), precision="exact", origin="user",
            time_kind="recorded", user_activity=True,
        ))
    if large:
        threads, points = [], []
        for i in range(100):
            tid = f"demo-scale-{i}"
            threads.append(TimelineThread(
                id=tid, title=f"Beispielvorhaben {i + 1}", status="active", tags=["arbeit" if i % 2 else "privat"],
                created_on=today - timedelta(days=730), last_user_activity=today - timedelta(days=44),
            ))
            for j in range(50):
                points.append(TimelinePoint(
                    id=f"{tid}-{j}", thread_id=tid, layer="activity", title=f"Rückmeldung {j + 1}",
                    summary="Fiktive Aktivität für die lokale Browserprobe.",
                    start=today - timedelta(days=730 - j * 14), precision="exact", origin="user",
                    time_kind="recorded", user_activity=True,
                ))
    return TimelineData(demo=True, today=today, threads=threads, points=points)
