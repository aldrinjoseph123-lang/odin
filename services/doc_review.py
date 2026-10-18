"""Customer uploads wait for staff review (17 Oct 2026, system-map loophole 65).

A file an outside account (a customer, reseller or contractor) uploads for an
upload ask (services/asks.py) is stored with `documents.review_status =
'pending'`; staff uploads are 'accepted' at once, and so is every document
from before this. While pending, a file is not opened by anyone (the download
route refuses it), is not mirrored to OneDrive, not read for search or AI, not
in a report, the sign-off or a stage gate, and partners do not see it in the
documents list. The ask counts as answered; the project manager (or anyone
who manages the rollout's documents) accepts it, which makes it a normal
document, or rejects it, which deletes the file, reopens the ask and tells the
partner. Routes: routes/projects.document_review.
"""
from datetime import datetime

from db import soft_delete
from services import asks

ACCEPTED = "accepted"
PENDING = "pending"
REJECTED = "rejected"


def ask_of(db, doc_id):
    """The upload ask the file answered, with who gave it: {task_id, title, by_id}, or None."""
    return db.execute("SELECT a.task_id, a.by_id, t.title FROM task_answers a JOIN tasks t ON t.id = a.task_id "
                      "WHERE a.question_key = ? AND a.value = ? AND t.kind = 'upload'", (asks.FILE_KEY, str(doc_id))).fetchone()


def _decide(db, doc_id, status, by):
    return db.execute("UPDATE documents SET review_status = ?, reviewed_by = ?, reviewed_at = ? WHERE id = ? AND review_status = ? AND deleted_at IS NULL",
                      (status, by, datetime.utcnow().isoformat(), doc_id, PENDING)).rowcount == 1


def accept(db, doc_id, by):
    """True when this call accepted it (False: decided a moment ago). Commits; the caller audits."""
    done = _decide(db, doc_id, ACCEPTED, by)
    db.commit()
    return done


def reject(db, doc_id, by):
    """(rejected?, the ask it answered or None). The file is soft deleted as the
    documents panel deletes one, and the ask is open again. Commits; the caller audits."""
    ask = ask_of(db, doc_id)
    if not _decide(db, doc_id, REJECTED, by):
        db.rollback()
        return False, None
    if ask:
        asks.reset(db, ask["task_id"])
    soft_delete("documents", doc_id)   # commits
    return True, ask
