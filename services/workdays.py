"""Working days: the working week (Settings → General) minus the holidays.

Stage lengths, SLAs and time in a stage count working days when the
workspace says so (policy count_working_days); gaps between two dates
("3 d late", "due in 5 d") stay calendar days. Holidays are one line each:
"2026-12-02 National Day", or a span "2027-03-20 to 2027-03-22 Eid al-Fitr".
"""
import re
from datetime import date, timedelta
from functools import lru_cache

from policies import WEEKDAYS, policy

LINE = re.compile(r"(\d{4}-\d{2}-\d{2})(?:\s+to\s+(\d{4}-\d{2}-\d{2}))?(?:\s+(.*))?")
MAX_SPAN = 31


def parse_holidays(text):
    """[(first, last, name)] from the policy text, or raise ValueError naming the line."""
    out = []
    for n, raw in enumerate((text or "").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        m = LINE.fullmatch(line)
        try:
            first = date.fromisoformat(m.group(1)) if m else None
            last = date.fromisoformat(m.group(2)) if m and m.group(2) else first
        except ValueError:
            first = None
        if not first or last < first or (last - first).days >= MAX_SPAN:
            raise ValueError(f'line {n}: a date like 2026-12-02, or "2027-03-20 to 2027-03-22", then a name')
        out.append((first, last, (m.group(3) or "").strip()[:80]))
    return sorted(out)


@lru_cache(maxsize=8)
def _calendar(week, text):
    days = set()
    for first, last, _ in parse_holidays(text):
        days.update(first + timedelta(days=i) for i in range((last - first).days + 1))
    return frozenset(WEEKDAYS.index(d) for d in week), frozenset(days)


def calendar(db=None):
    """(working weekday numbers, holiday dates); none when durations count calendar days."""
    if not policy("count_working_days", db):
        return frozenset(range(7)), frozenset()
    return _calendar(tuple(policy("working_days", db)), policy("holidays", db))


def is_workday(d, cal):
    week, off = cal
    return d.weekday() in week and d not in off


def add(start, n, cal):
    """The date n working days after start (n <= 0: start itself)."""
    if not cal[0]:   # no working day at all: fall back to calendar days
        return start + timedelta(days=max(n, 0))
    d = start
    while n > 0:
        d += timedelta(days=1)
        if is_workday(d, cal):
            n -= 1
    return d


def between(a, b, cal):
    """Working days from a to b: those in (a, b], negative when b is before a."""
    if not a or not b:
        return None
    if b < a:
        return -between(b, a, cal)
    return sum(1 for i in range(1, (b - a).days + 1) if is_workday(a + timedelta(days=i), cal))


def off_between(a, b, cal):
    """Non-working dates in (a, b]."""
    return (b - a).days - between(a, b, cal) if b > a else 0


if __name__ == "__main__":
    week = (frozenset(range(5)), frozenset({date(2026, 12, 2)}))   # Mon–Fri, a Wednesday off
    assert add(date(2026, 11, 27), 1, week) == date(2026, 11, 30)          # Fri + 1 = Mon
    assert add(date(2026, 11, 30), 3, week) == date(2026, 12, 4)           # skips the Wednesday
    assert between(date(2026, 11, 27), date(2026, 12, 4), week) == 4      # Mon, Tue, Thu, Fri
    assert between(date(2026, 12, 4), date(2026, 11, 27), week) == -4
    assert off_between(date(2026, 11, 27), date(2026, 12, 4), week) == 3  # Sat, Sun, Wed
    assert parse_holidays("2027-03-20 to 2027-03-22 Eid\n\n2026-12-02 National Day")[0][2] == "National Day"
    for bad in ("02/12/2026 X", "2026-12-05 to 2026-12-01", "2026-01-01 to 2026-03-01"):
        try:
            parse_holidays(bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    print("ok")
