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
    runs: str = "on_demand"         # on_demand | nightly | daily (the morning brief, at its own time) | at_event
    scope: str = "project"          # project: gather(project_id=…), kept as a suggestion on it; portfolio: gather(), kept as the latest answer;
                                    # person: gather(user_id=…), handed to on_new (the morning brief), not kept
    takes_input: bool = False       # on-demand features that work on text the person sent: gather(project_id=…, given=…)
    chunks: Optional[Callable] = None   # chunks(inputs) -> [inputs, …]: input too long for one request, asked in parts…
    merge: Optional[Callable] = None    # …and merge([output, …]) -> output joins the answers before refine
    options: Optional[Callable] = None  # options(project_id) -> dict the page needs to ask (e.g. which documents)
    on_new: Optional[Callable] = None   # on_new(db, project_id, output): after a night-shift answer (tell someone it is there)
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


MAX_REPLY_TOKENS = 1000   # under the server's 1,024-token cap per reply (integration guide)


def system_prompt(prompt_file):
    """The identity line (policy ai_identity; the AI server's guide asks every
    application to start with it) and then the feature's own instructions."""
    from policies import policy
    with open(os.path.join(PROMPTS, prompt_file), encoding="utf-8") as fh:
        text = fh.read().strip()
    identity = policy("ai_identity").strip()
    return f"{identity}\n\n{text}" if identity else text


def prompt_of(feature):
    """(system prompt, hash): the hash goes into every answer and every check,
    so an edited prompt, or a new identity line, must pass validation again."""
    text = system_prompt(feature.prompt)
    return text, hashlib.sha256(text.encode()).hexdigest()[:12]


def _dump(inputs):
    return json.dumps(inputs, ensure_ascii=False, default=str)


def fit(inputs, limit):
    """The inputs, trimmed until their JSON is at most `limit` characters
    (policy ai_max_input_chars): the longest text is halved first, then the
    longest list loses its last item. Facts at the start of each text and
    list are kept; reading is the slow part on a CPU server."""
    import copy
    if len(_dump(inputs)) <= limit:
        return inputs
    inputs = copy.deepcopy(inputs)

    def walk(node):
        items = node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else ()
        for k, v in items:
            yield node, k, v
            yield from walk(v)
    while len(_dump(inputs)) > limit:
        leaves = list(walk(inputs))
        texts = [(len(v), n, k) for n, k, v in leaves if isinstance(v, str)]
        lists = [(len(v), v) for _n, _k, v in leaves if isinstance(v, list)]
        longest = max(texts, key=lambda t: t[0], default=(0, None, None))
        if longest[0] > 160:
            n, k = longest[1], longest[2]
            n[k] = n[k][: len(n[k]) // 2].rstrip() + "…"
        elif lists and max(lists, key=lambda x: x[0])[0] > 1:
            max(lists, key=lambda x: x[0])[1].pop()
        else:
            break
    return inputs


def messages_for(feature, inputs):
    """System prompt and the inputs as JSON. Keys starting with "_" are Odin's
    own bookkeeping (links for refine) and never reach the model."""
    from policies import policy
    text, _ = prompt_of(feature)
    if isinstance(inputs, dict):
        inputs = {k: v for k, v in inputs.items() if not k.startswith("_")}
    return [{"role": "system", "content": text},
            {"role": "user", "content": _dump(fit(inputs, policy("ai_max_input_chars")))}]


def run(feature, inputs, cfg=None, log=None):
    """Ask the server. One retry when the answer does not match its form;
    any other failure raises AIError. Returns (output, meta) with meta =
    {model, seconds, usage, prompt_hash}. `log` names the job, project and
    person for the call log."""
    cfg = cfg or config()
    log = {"feature": feature.key, **(log or {})}
    tokens = min(feature.max_tokens, MAX_REPLY_TOKENS)
    parts = feature.chunks(inputs) if feature.chunks else [inputs]
    outs, seconds = [], 0.0
    for part in parts:
        msgs = messages_for(feature, part)
        try:
            out, meta = chat(cfg, msgs, feature.schema, tokens, feature.temperature, log=log)
        except AIError as exc:
            if exc.kind != "invalid":
                raise
            out, meta = chat(cfg, msgs, feature.schema, tokens, feature.temperature, log=log)
        outs.append(out)
        seconds += meta["seconds"]
    out = feature.merge(outs) if feature.merge else outs[0]
    meta["seconds"], meta["parts"] = round(seconds, 1), len(parts)
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
        st = json.loads(row[0]) if row else {"state": "unknown"}
    except ValueError:
        return {"state": "unknown"}
    # a heartbeat older than two beats (15 min at least) says nothing about now:
    # the worker may be stopped (D15). The gate treats it as not up.
    from datetime import datetime, timedelta
    limit = max(15, 2 * policy("ai_heartbeat_minutes", db))
    if st.get("checked_at") and st["checked_at"] < (datetime.utcnow() - timedelta(minutes=limit)).isoformat():
        st = {**st, "stale": True, "no_heartbeat_since": st["checked_at"]}
    return st


STALE_KEYS = ("stale", "no_heartbeat_since")   # read-time flags, never stored


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
    if st.get("stale"):
        return f"No heartbeat from the AI server since {st['no_heartbeat_since'][:16].replace('T', ' ')} UTC"
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


def latest_project(key, project_id, db=None, max_age_hours=36):
    """A project feature's newest unused answer, when the gate is open now and
    it is recent: the payload, or None."""
    from datetime import datetime, timedelta
    from db import get_db
    db = db or get_db()
    if gate(key, db):
        return None
    row = db.execute("SELECT payload FROM ai_suggestions WHERE project_id = ? AND feature = ? AND status = 'new' AND created_at >= ? ORDER BY id DESC LIMIT 1",
                     (project_id, key, (datetime.utcnow() - timedelta(hours=max_age_hours)).isoformat())).fetchone()
    return json.loads(row[0]) if row else None


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
