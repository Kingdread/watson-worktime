"""Imports the watson data."""
import datetime
import json
import os
from collections import defaultdict
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config


class Weekday(StrEnum):
    MONDAY = "mo"
    TUESDAY = "tu"
    WEDNESDAY = "we"
    THURSDAY = "th"
    FRIDAY = "fr"
    SATURDAY = "sa"
    SUNDAY = "su"

    @classmethod
    def from_date(cls, date: datetime.date) -> "Weekday":
        return list(cls)[date.weekday()]

    @classmethod
    def from_str(cls, value: str) -> "Weekday":
        for weekday in cls:
            if value.lower().startswith(weekday.value):
                return weekday


def watson_dir() -> Path:
    """Retrieves the watson directory in effect."""
    watson_dir = os.getenv("WATSON_DIR")
    if watson_dir:
        return Path(watson_dir)
    return Path.home() / ".config" / "watson"


def clamp(dt: datetime.datetime, date: datetime.date) -> datetime.datetime:
    if dt.date() < date:
        return datetime.datetime.combine(date, datetime.time.min)
    if dt.date() > date:
        return datetime.datetime.combine(date, datetime.time.max)
    return dt


class Frame(NamedTuple):
    start: datetime.datetime
    stop: datetime.datetime

    def duration_on(self, date: datetime.date) -> datetime.timedelta:
        """Returns the portion of the frame that lies on the given day."""
        return clamp(self.stop, date) - clamp(self.start, date)

    def dates(self) -> list[datetime.date]:
        """Returns a list of dates that this frame entails."""
        def _generate():
            current = self.start.date()
            while current <= self.stop.date():
                yield current
                current += datetime.timedelta(days=1)
        return list(_generate())


def load_frames(include_current=False) -> list[Frame]:
    with open(watson_dir() / "frames") as framefile:
        data = json.load(framefile)
    frames = [
        Frame(
            start=datetime.datetime.fromtimestamp(row[0]),
            stop=datetime.datetime.fromtimestamp(row[1]),
        )
        for row in data
    ]
    if include_current:
        try:
            with open(watson_dir() / "state") as statefile:
                data = json.load(statefile)
            data["start"]
        except (FileNotFoundError, KeyError):
            pass
        else:
            frame = Frame(
                start=datetime.datetime.fromtimestamp(data["start"]),
                stop=datetime.datetime.now().replace(microsecond=0),
            )
            frames.append(frame)
    return frames


class Day:
    """Summary for a day."""

    def __init__(self, date: datetime.date, worktime: datetime.timedelta = datetime.timedelta()):
        self.date = date
        self.worktime = worktime

    def insert(self, frame: Frame):
        """Insert the given frame into the workday."""
        self.worktime += frame.duration_on(self.date)

    def expected_worktime(self, config: "Config") -> datetime.timedelta:
        if self.date in config.holidays() or self.date in (config.vacation() | config.ignored()):
            return datetime.timedelta(0)
        if Weekday.from_date(self.date) in config.workdays():
            return config.worktime_per_day()
        return datetime.timedelta(0)

    def overtime(self, config: "Config") -> datetime.timedelta:
        if self.date in config.ignored():
            # The convention is to just ignore everything on ignored days, even
            # if additional work has been done.
            return datetime.timedelta(0)
        return self.worktime - self.expected_worktime(config)

    def get_date(self):
        return self.date

class Calendar:
    def __init__(self, frames: Optional[Iterable[Frame]] = None):
        self.days: dict[datetime.date, Day] = {}
        for frame in frames or []:
            self.insert(frame)

    def insert(self, frame: Frame):
        for date in frame.dates():
            self.days.setdefault(date, Day(date)).insert(frame)

    def __getitem__(self, key):
        return self.days.get(key, Day(key))


__all__ = ["watson_dir", "Frame", "load_frames", "Calendar"]
