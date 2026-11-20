import re
from dataclasses import dataclass

from app.api.schemas import ChatRequest

# 8+ digits, even when split by spaces or dashes (phone, account, card numbers).
# \d also matches Bangla digits.
LONG_NUMBER = re.compile(r"(?:\d[\s-]?){8,}")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# Answers to these change over time. A false skip only costs money;
# a stale cached answer costs trust. Skipping is the safe direction.
TIME_WORDS = {
    "today", "tonight", "now", "current", "currently", "latest", "tomorrow", "yesterday",
    "ajke", "aj", "ajker", "ekhon", "kal",
    "আজ", "আজকে", "আজকের", "এখন", "বর্তমান", "আগামীকাল", "গতকাল", "কাল",
}
# Split on whitespace, not \w: Bangla vowel signs are not "word" characters in Python regex.
STRIP = ".,!?;:\"'()[]{}।"


@dataclass(frozen=True)
class Decision:
    cacheable: bool
    reason: str | None = None


def cache_decision(req: ChatRequest) -> Decision:
    for m in req.messages:
        if LONG_NUMBER.search(m.content) or EMAIL.search(m.content):
            return Decision(False, "personal-data")
        tokens = {t.strip(STRIP) for t in m.content.lower().split()}
        if tokens & TIME_WORDS:
            return Decision(False, "time-sensitive")
    return Decision(True)