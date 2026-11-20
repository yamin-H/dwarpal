import pytest

from app.api.schemas import ChatRequest, Message
from app.cache.policy import cache_decision


def req(text, role="user"):
    return ChatRequest(messages=[Message(role=role, content=text)])


@pytest.mark.parametrize("text", [
    "How much zakat do I owe?", "যাকাত কত টাকা দিতে হয়?",
    "zakat koto taka dite hoy", "ফজরের নামাজ কত রাকাত?",
])
def test_normal_questions_are_cacheable(text):
    assert cache_decision(req(text)).cacheable


@pytest.mark.parametrize("text", [
    "call me on 01712345678", "my account is 1234 5678 9012",
    "আমার নম্বর ০১৭১২৩৪৫৬৭৮", "mail me at rahim@example.com",
])
def test_personal_data_is_not_cacheable(text):
    d = cache_decision(req(text))
    assert not d.cacheable and d.reason == "personal-data"


@pytest.mark.parametrize("text", [
    "what is the prayer time today?", "আজকে নামাজের সময় কখন?",
    "namaz er time ajke koyta", "latest gold price?",
])
def test_time_sensitive_is_not_cacheable(text):
    d = cache_decision(req(text))
    assert not d.cacheable and d.reason == "time-sensitive"


def test_system_messages_are_checked_too():
    assert not cache_decision(req("Today's date is fixed", role="system")).cacheable