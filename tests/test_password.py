from homebase.password import hash_password, verify_password


def test_correct_password_verifies():
    stored = hash_password("open sesame")

    assert verify_password("open sesame", stored)


def test_wrong_password_is_rejected():
    stored = hash_password("open sesame")

    assert not verify_password("open sesam", stored)


def test_same_password_hashes_differently_each_time():
    assert hash_password("open sesame") != hash_password("open sesame")


def test_hash_is_safe_to_put_in_an_env_file():
    stored = hash_password("open sesame")

    assert "$" not in stored
    assert " " not in stored
    assert "open sesame" not in stored


def test_malformed_or_missing_hash_never_verifies():
    assert not verify_password("anything", "")
    assert not verify_password("anything", "not-a-hash")
