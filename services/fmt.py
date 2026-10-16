"""Small text helpers shared by the reports, the sign-off and the messages."""
from datetime import date


def iso_date(iso):
    """A date from a stored date or timestamp, or None for one that is empty, malformed
    or absurd: one bad task date must not take the whole PDF (and the weekly
    email's attachments) down with it (P8)."""
    try:
        d = date.fromisoformat(str(iso)[:10]) if iso else None
    except ValueError:
        return None
    return d if d and 1900 <= d.year <= 2200 else None


def fmt_date(iso, empty="-"):
    """'3 Oct 2026' from a stored date or timestamp; `empty` when there is none to show."""
    d = iso_date(iso)
    return f"{d.day} {d.strftime('%b %Y')}" if d else empty


def plural(n, word, many=None):
    """`word` when n is 1, else `many` (default: word + 's'): f"{n} {plural(n, 'task')}"."""
    return word if n == 1 else many or word + "s"
