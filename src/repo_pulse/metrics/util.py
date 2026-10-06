from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone


def ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


@dataclass(frozen=True)
class Windows:
    as_of: datetime
    days: int

    @classmethod
    def of(cls, as_of: str, days: int) -> "Windows":
        d = date.fromisoformat(as_of)
        return cls(datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1), days)

    @property
    def cur(self) -> tuple[datetime, datetime]:
        return self.as_of - timedelta(days=self.days), self.as_of

    @property
    def prior(self) -> tuple[datetime, datetime]:
        return self.as_of - timedelta(days=2 * self.days), self.as_of - timedelta(days=self.days)

    def both(self):
        return {"cur": self.cur, "prior": self.prior}


def within(t: datetime | None, w: tuple[datetime, datetime]) -> bool:
    return t is not None and w[0] <= t < w[1]


def days(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 86400


def quantile(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 2)


def ratio(n: float, d: float) -> float | None:
    return round(n / d, 3) if d else None


def status(value, rule: dict | None) -> str:
    """green / amber / red from config thresholds; 'na' when not applicable."""
    if value is None or not rule:
        return "na"
    lower = rule.get("lower_is_better", False)
    good, bad = rule["good"], rule["bad"]
    if lower:
        return "green" if value <= good else "red" if value >= bad else "amber"
    return "green" if value >= good else "red" if value <= bad else "amber"


def kpi(key: str, label: str, cur, prior=None, unit: str = "", rule: dict | None = None, note: str = "",
        source: str = "", lower_is_better: bool | None = None) -> dict:
    delta = None
    if isinstance(cur, (int, float)) and isinstance(prior, (int, float)):
        delta = round(cur - prior, 3)
    lib = rule.get("lower_is_better", False) if rule else bool(lower_is_better)
    return {"key": key, "label": label, "value": cur, "prior": prior, "delta": delta, "unit": unit,
            "status": status(cur, rule), "lower_is_better": lib, "note": note, "source": source}


def weekly(dates: list[datetime], start: datetime, end: datetime) -> list[list]:
    """Counts per ISO week (Monday) between start and end; complete weeks only (a partial last week reads as a drop)."""
    s = (start - timedelta(days=start.weekday())).date()
    buckets: dict[str, int] = {}
    d = s
    while d + timedelta(days=7) <= end.date():
        buckets[d.isoformat()] = 0
        d += timedelta(days=7)
    for t in dates:
        if start <= t < end:
            wk = (t - timedelta(days=t.weekday())).date().isoformat()
            if wk in buckets:
                buckets[wk] += 1
    return [[k, v] for k, v in buckets.items()]
