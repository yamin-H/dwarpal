from app.core.keys import PREFIX, generate_key, hash_key


def test_generate_key_format_and_uniqueness():
    a, b = generate_key(), generate_key()
    assert a.startswith(PREFIX)
    assert a != b


def test_hash_is_deterministic_and_not_the_key():
    k = generate_key()
    assert hash_key(k) == hash_key(k)
    assert hash_key(k) != k
    assert len(hash_key(k)) == 64