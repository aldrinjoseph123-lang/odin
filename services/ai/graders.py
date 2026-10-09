"""Graders for AI feature validation. Each returns a function
grader(inputs, output) -> a problem sentence, or None when the answer is fine.
They check what a small model gets wrong in ways a reader would mind: facts
dropped or changed, a verdict the input contradicts, answers too long, lists
that miss what was there to find."""


def _text(value):
    """Every string in an answer, joined: graders read the whole answer."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_text(v) for v in value)
    return str(value)


def facts_kept(*facts):
    """Each fact (a name, a date, a number as written) appears in the answer."""
    def grade(inputs, output):
        text = _text(output).lower()
        missing = [f for f in facts if f.lower() not in text]
        return f"left out {', '.join(missing)}" if missing else None
    grade.__name__ = "facts_kept"
    return grade


def never_says(*phrases):
    """None of these phrases appear: a verdict the input contradicts."""
    def grade(inputs, output):
        text = _text(output).lower()
        said = [p for p in phrases if p.lower() in text]
        return f"said \"{said[0]}\", which the facts contradict" if said else None
    grade.__name__ = "never_says"
    return grade


def mentions_any(*options, what=None):
    """At least one of these wordings appears (the same fact, said either way)."""
    def grade(inputs, output):
        text = _text(output).lower()
        return None if any(o.lower() in text for o in options) else f"left out {what or options[0]}"
    grade.__name__ = "mentions_any"
    return grade


def max_words(field, n):
    def grade(inputs, output):
        words = len(_text(output.get(field, "")).split())
        return f"{field} has {words} words (limit {n})" if words > n else None
    grade.__name__ = "max_words"
    return grade


def finds(field, expected, at_least=0.8):
    """An extraction finds at least this share of the known items (each
    matched by a key word appearing in the list)."""
    def grade(inputs, output):
        text = _text(output.get(field, [])).lower()
        found = [e for e in expected if e.lower() in text]
        share = len(found) / len(expected) if expected else 1
        if share < at_least:
            return f"{field} found {len(found)} of {len(expected)} known items ({', '.join(e for e in expected if e not in found)} missing)"
        return None
    grade.__name__ = "finds"
    return grade
