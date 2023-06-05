import copy
import datetime
import tomllib
from typing import Optional

import holidays
from holidays.holiday_base import HolidayBase

from .data import watson_dir, Weekday


DEFAULT_CONFIG = {
    "country": "DE",
    "state": "BW",
    "hours-per-day": 8,
    "workdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
    "inception": "1970-01-01",
    "vacation_per_year": 30
}


class Config:
    def __init__(self):
        self.data = copy.copy(DEFAULT_CONFIG)
        self.vacation_days = set()

    def load(self):
        self._load_config()
        self._load_vacation()

    def _load_config(self):
        path = watson_dir() / "worktime.toml"
        try:
            with open(path, "rb") as reader:
                data = tomllib.load(reader)
        except FileNotFoundError:
            pass
        else:
            self.data.update(data)

    def _load_vacation(self):
        path = watson_dir() / "vacation-days"
        try:
            with open(path) as reader:
                for line in reader:
                    day = datetime.date.fromisoformat(line.strip())
                    self.vacation_days.add(day)
        except FileNotFoundError:
            pass

    def save(self):
        self._save_vacation()

    def _save_vacation(self):
        path = watson_dir() / "vacation-days"
        path.write_text("\n".join(day.isoformat() for day in self.vacation()))

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

    def workdays(self) -> list[Weekday]:
        return [Weekday.from_str(value) for value in self.data["workdays"]]

    def inception(self) -> datetime.date:
        return datetime.date.fromisoformat(self.data["inception"])

    def vacation_per_year(self) -> int:
        return self.data["vacation_per_year"]
