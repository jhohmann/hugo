"""Passwort-Hash erzeugen: python -m app.passwords (verdeckte Eingabe)."""

import hashlib
import hmac
import secrets
from getpass import getpass


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=32768, r=8, p=3,
        maxmem=64 * 1024 * 1024, dklen=32,
    )


def parse_hash(encoded: str) -> tuple[bytes, bytes]:
    version, salt_hex, digest_hex = encoded.split(":")
    salt, digest = bytes.fromhex(salt_hex), bytes.fromhex(digest_hex)
    if version != "scrypt-v1" or len(salt) != 16 or len(digest) != 32:
        raise ValueError("Ungültiger Passwort-Hash")
    return salt, digest


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 1024:
        raise ValueError("Bitte 12 bis 1024 Zeichen verwenden.")
    salt = secrets.token_bytes(16)
    return f"scrypt-v1:{salt.hex()}:{_derive(password, salt).hex()}"


def verify_password(password: str, encoded: str) -> bool:
    if not password or len(password) > 1024:
        return False
    salt, expected = parse_hash(encoded)
    return hmac.compare_digest(_derive(password, salt), expected)


if __name__ == "__main__":
    password = getpass("Hugo-Passwort (mindestens 12 Zeichen): ")
    if password != getpass("Passwort wiederholen: "):
        raise SystemExit("Passwörter stimmen nicht überein.")
    try:
        print("HUGO_PASSWORD_HASH=" + hash_password(password))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
