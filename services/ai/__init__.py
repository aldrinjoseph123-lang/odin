"""Odin's AI framework.

A feature is one AIFeature spec registered in FEATURES (like policies.POLICIES
or doc_templates.KINDS): its prompt, the JSON form its answer must take, how it
gathers its input, what to do instead when the AI cannot be used, and a
synthetic test project with graders that prove it works on the model the
server runs today. The framework does the rest for every feature alike:

- client.py   the OpenAI-compatible call, the address guard, the form check
- health.py   the heartbeat, the model fingerprint, validation, the job queue
- here        the registry, the gate, and run()

The gate: a feature runs only when AI is switched on, the server is up, the
feature is switched on, and it passed validation on the model the server runs
now with the prompt this release ships (or an admin forced it on). Anything
else means the caller falls back to today's behaviour. Nothing outside this
package talks to the AI server (a meta-test enforces it).
"""
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Callable, Optional

from services.ai.client import AIError, chat, config

PROMPTS = os.path.join(os.path.dirname(__file__), "prompts")
STATUS_SETTING = "ai.status"
GOOD_STATES = ("passed", "slow")


@dataclass(frozen=True)
class AIFeature:
    key: str                        # stable id, used in settings and history
    label: str                      # what admins see in Settings → AI
    description: str                # one sentence: what it does for whom
    prompt: str                     # file in services/ai/prompts, versioned in its name (weekly_words.v1.txt)
    schema: dict                    # the JSON form the answer must take
    gather: Callable[..., dict]     # gather(**context) -> the inputs the model sees (scope already applied)
    fixture: Callable[[], dict]     # a synthetic project's inputs: never customer data
    graders: tuple                  # grader(inputs, output) -> a problem sentence, or None
    fallback: Optional[Callable] = None   # today's behaviour, used when the gate is closed
    runs: str = "on_demand"         # on_demand | nightly | at_event
    scope: str = "project"          # project: gather(project_id=…), kept as a suggestion on it; portfolio: gather(), kept as the latest answer
    max_tokens: int = 800
    budget_s: Optional[int] = None  # slower than this = "slow"; None = the ai_budget_s policy
    temperature: float = 0.3
    project_role: Optional[str] = "manage_project"   # who may ask for it and see its suggestions (constants.PROJECT_ACTIONS); None = all staff who see the rollout
    refine: Optional[Callable] = None       # refine(inputs, output) -> output: Odin's own checks after the form check (drop what the input does not support)
    extra: dict = field(default_factory=dict)


FEATURES = {}


def register(feature):
    """Add a feature to the registry. Refuses a spec that cannot be validated."""
    if feature.key in FEATURES:
        raise ValueError(f"AI feature {feature.key} registered twice")
    if not feature.graders or not callable(feature.fixture):
        raise ValueError(f"AI feature {feature.key} needs a fixture and graders")
    if not os.path.exists(os.path.join(PROMPTS, feature.prompt)):
        raise ValueError(f"AI feature {feature.key}: prompt {feature.prompt} not found")
    FEATURES[feature.key] = feature
    return feature


def prompt_of(feature):
    """(text, hash): the hash goes into every answer and every check, so an
    edited prompt is a new prompt that must pass validation again."""
    with open(os.path.join(PROMPTS, feature.prompt), encoding="utf-8") as fh:
        text = fh.read().strip()
    return text, hashlib.sha256(text.encode()).hexdigest()[:12]


def messages_for(feature, inputs):
    text, _ = prompt_of(feature)
    return [{"role": "system", "content": text},
            {"role": "user", "content": json.dumps(inputs, ensure_ascii=False, indent=1, default=str)}]


def run(feature, inputs, cfg=None):
    """Ask the server. One retry when the answer does not match its form;
    any other failure raises AIError. Returns (output, meta) with meta =
    {model, seconds, usage, prompt_hash}."""
    cfg = cfg or config()
    msgs = messages_for(feature, inputs)
    try:
        out, meta = chat(cfg, msgs, feature.schema, feature.max_tokens, feature.temperature)
    except AIError as exc:
        if exc.kind != "invalid":
            raise
        out, meta = chat(cfg, msgs, feature.schema, feature.max_tokens, feature.temperature)
    if feature.refine:
        out = feature.refine(inputs, out)
    meta["prompt_hash"] = prompt_of(feature)[1]
    return out, meta


def status(db=None):
    """The heartbeat's last word: {state, since, checked_at, misses,
    fingerprint, model, error}. state is off | unknown | up | down."""
    from db import get_db
    from policies import policy
    db = db or get_db()
    if not policy("ai_enabled", db) or not policy("ai_base_url", db):
        return {"state": "off"}
    row = db.execute("SELECT value FROM settings WHERE key = ?", (STATUS_SETTING,)).fetchone()
    try:
        return json.loads(row[0]) if row else {"state": "unknown"}
    except ValueError:
        return {"state": "unknown"}


def switch(key, db=None):
    """(on, forced) for one feature: on by default; forced = run even
    without a passed validation (an admin's audited choice)."""
    from db import get_db
    db = db or get_db()
    rows = dict(db.execute("SELECT key, value FROM settings WHERE key IN (?, ?)", (f"ai.feature.{key}", f"ai.feature.{key}.force")).fetchall())
    return rows.get(f"ai.feature.{key}", "1") == "1", rows.get(f"ai.feature.{key}.force") == "1"


def latest_check(key, db=None, current=True):
    """The newest validation of a feature; with current=True only one made on
    the model the server runs now with the prompt this release ships."""
    from db import get_db
    db = db or get_db()
    feature = FEATURES[key]
    if current:
        fp = status(db).get("fingerprint")
        return db.execute("SELECT * FROM ai_checks WHERE kind = 'feature' AND feature = ? AND fingerprint = ? AND prompt_hash = ? ORDER BY id DESC LIMIT 1",
                          (key, fp, prompt_of(feature)[1])).fetchone() if fp else None
    return db.execute("SELECT * FROM ai_checks WHERE kind = 'feature' AND feature = ? ORDER BY id DESC LIMIT 1", (key,)).fetchone()


def gate(key, db=None):
    """None when the feature may run now, else the reason it may not."""
    st = status(db)
    if st["state"] == "off":
        return "AI is switched off (Settings → AI)"
    if st["state"] != "up":
        return "The AI server is not answering"
    on, forced = switch(key, db)
    if not on:
        return "This AI feature is switched off"
    if forced:
        return None
    check = latest_check(key, db)
    if not check:
        return "Not yet validated on the current model"
    if check["state"] not in GOOD_STATES:
        return "Failed validation on the current model"
    return None


def latest_portfolio(key, db=None, max_age_hours=36):
    """A portfolio feature's latest answer, when the gate is open now and it
    is recent: (payload, meta) or None (the caller leaves it out)."""
    from datetime import datetime, timedelta
    from db import get_db
    db = db or get_db()
    if gate(key, db):
        return None
    row = db.execute("SELECT value FROM settings WHERE key = ?", (f"ai.latest.{key}",)).fetchone()
    if not row:
        return None
    rec = json.loads(row[0])
    if rec["created_at"] < (datetime.utcnow() - timedelta(hours=max_age_hours)).isoformat():
        return None
    return rec["payload"], rec


def complete(key, **context):
    """The door every feature goes through: gate, gather, ask. Returns
    (output, meta), or raises AIError (gate closed or the call failed); the
    caller then uses the feature's fallback."""
    reason = gate(key)
    if reason:
        raise AIError(reason, "gate")
    feature = FEATURES[key]
    return run(feature, feature.gather(**context))


# Features register themselves on import.
from services.ai import features  # noqa: E402,F401
