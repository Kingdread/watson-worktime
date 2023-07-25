import copy
import datetime
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Optional

import holidays
from holidays.holiday_base import HolidayBase

from .data import watson_dir, Weekday


DEFAULT_CONFIG = {
    "country": "DE",
    "state": "BW",
    "hours-per-day": 8,
    "workdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
    "vacation-per-year": 30,
    "total-format": "exact",
    "day-list": "full",
}


class DayListStyle(StrEnum):
    FULL = "full"
    NONE = "none"
    TRUNCATE = "truncate"


def load_days(path: Path) -> set[datetime.date]:
    result = set()
    try:
        with open(path, "r", encoding="utf-8") as reader:
            for line in reader:
                day = datetime.date.fromisoformat(line.strip())
                result.add(day)
    except FileNotFoundError:
        pass
    return result


def save_days(path: Path, days: set[datetime.date]):
    sorted_days = list(days)
    sorted_days.sort()
    path.write_text("\n".join(day.isoformat() for day in sorted_days))


class Config:
    def __init__(self):
        self.data = copy.copy(DEFAULT_CONFIG)
        self.vacation_days = set()
        self.ignored_days = set()

    def load(self):
        self._load_config()
        self.vacation_days = load_days(watson_dir() / "vacation-days")
        self.ignored_days = load_days(watson_dir() / "ignored-days")

    def _load_config(self):
        path = watson_dir() / "worktime.toml"
        try:
            with open(path, "rb") as reader:
                data = tomllib.load(reader)
        except FileNotFoundError:
            pass
        else:
            self.data.update(data)

    def save(self):
        save_days(watson_dir() / "vacation-days", self.vacation())
        save_days(watson_dir() / "ignored-days", self.ignored())

    def worktime_per_day(self) -> datetime.timedelta:
        return datetime.timedelta(hours=self.data["hours-per-day"])

    def country(self) -> str:
        return self.data["country"]

    def subdiv(self) -> Optional[str]:
        return self.data["state"]

    def holidays(self) -> HolidayBase:
        return holidays.country_holidays(self.country(), subdiv=self.subdiv())

    def vacation(self) -> set[datetime.date]:
        return self.vacation_days

    def add_vacation(self, day: datetime.date):
        self.vacation_days.add(day)

    def remove_vacation(self, day: datetime.date):
        self.vacation_days.remove(day)

    def ignored(self) -> set[datetime.date]:
        return self.ignored_days

    def add_ignored(self, day: datetime.date):
        self.ignored_days.add(day)

    def remove_ignored(self, day: datetime.date):
        self.ignored_days.remove(day)

    def workdays(self) -> list[Weekday]:
        return [Weekday.from_str(value) for value in self.data["workdays"]]

    def inception(self) -> Optional[datetime.date]:
        if "inception" in self.data:
            return self.data["inception"]
        return None

    def vacation_per_year(self) -> int:
        return self.data["vacation-per-year"]

    def total_format(self) -> str:
        return self.data["total-format"]

    def day_list(self) -> DayListStyle:
        return DayListStyle(self.data["day-list"].lower())
