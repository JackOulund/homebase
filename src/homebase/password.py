import base64
import getpass
import hashlib
import hmac
import secrets
import sys

SCHEME = "scrypt"
COST = 2**14
BLOCK_SIZE = 8
PARALLELISM = 1
KEY_LENGTH = 32
MINIMUM_LENGTH = 12


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = _derive_key(password, salt, COST, BLOCK_SIZE, PARALLELISM)
    return ":".join(
        [
            SCHEME,
            str(COST),
            str(BLOCK_SIZE),
            str(PARALLELISM),
            _encode(salt),
            _encode(key),
        ]
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, cost, block_size, parallelism, salt, expected_key = stored_hash.split(
            ":"
        )
        if scheme != SCHEME:
            return False
        actual_key = _derive_key(
            password, _decode(salt), int(cost), int(block_size), int(parallelism)
        )
        return hmac.compare_digest(actual_key, _decode(expected_key))
    except ValueError:
        return False


def _derive_key(
    password: str, salt: bytes, cost: int, block_size: int, parallelism: int
) -> bytes:
    return hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=cost,
        r=block_size,
        p=parallelism,
        dklen=KEY_LENGTH,
    )


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode()


def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text.encode())


def main() -> None:
    password = getpass.getpass("New password: ")
    if len(password) < MINIMUM_LENGTH:
        sys.exit(f"Use at least {MINIMUM_LENGTH} characters.")
    if getpass.getpass("Repeat it: ") != password:
        sys.exit("The two entries differ.")
    print(f"LOGIN_PASSWORD_HASH={hash_password(password)}")


if __name__ == "__main__":
    main()
