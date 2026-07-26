from __future__ import annotations

import base64
import hashlib
import secrets
import time

SIGNING_ALPHABET = "AB45STUVWZEFGJ6CH01D237IXYPQRKLMN89"
TOKEN_SEEDS = ("唉？！云朵！", "哒哒哒哒哒，好想玩原神", "云！原！神！")


def _vm(value: int) -> int:
    if value & 128:
        return ((value << 1) ^ 27) & 255
    return value << 1


def _qm(value: int) -> int:
    return _vm(value) ^ value


def _mm(value: int) -> int:
    return _qm(_vm(value))


def _ym(value: int) -> int:
    return _mm(_qm(_vm(value)))


def _gm(value: int) -> int:
    return _ym(value) ^ _mm(value) ^ _qm(value)


def _mixed(values: list[int]) -> tuple[int, int, int, int, int, int]:
    return (
        _gm(values[0]) ^ _ym(values[1]) ^ _mm(values[2]) ^ _qm(values[3]),
        _qm(values[0]) ^ _gm(values[1]) ^ _ym(values[2]) ^ _mm(values[3]),
        _mm(values[0]) ^ _qm(values[1]) ^ _gm(values[2]) ^ _ym(values[3]),
        _ym(values[0]) ^ _mm(values[1]) ^ _qm(values[2]) ^ _gm(values[3]),
        values[4],
        values[5],
    )


def _av(value: str, key: str, trim: int) -> str:
    alphabet = key[: len(key) + trim]
    return "".join(alphabet[ord(char) % len(alphabet)] for char in value)


def _sv(value: str, key: str) -> str:
    return "".join(key[ord(char) % len(key)] for char in value)


def _interleave(values: list[str]) -> str:
    longest = values[2]
    chunks: list[str] = []
    for index in range(len(longest)):
        for value in values:
            if index < len(value):
                chunks.append(value[index])
    return "".join(chunks)


def build_hkey(request_path: str, timestamp: int, nonce: str) -> str:
    values = [
        _av(str(timestamp), SIGNING_ALPHABET, -2),
        _sv(request_path, SIGNING_ALPHABET),
        _sv(nonce, SIGNING_ALPHABET),
    ]
    values.sort(key=len)
    digest = hashlib.md5(_interleave(values).encode("utf-8")[:20]).hexdigest()
    mixed = _mixed([ord(char) for char in digest[-6:]])
    suffix = f"{sum(mixed) % 100:02d}"
    return _av(digest[:5], SIGNING_ALPHABET, -4) + suffix


def generate_nonce(timestamp: int | None = None) -> str:
    now = int(timestamp if timestamp is not None else time.time())
    upper_bound = max(int(time.time() * 1000), 2)
    random_value = secrets.randbelow(upper_bound)
    return hashlib.md5(f"{now}{random_value}".encode("ascii")).hexdigest().upper()


def get_request_keys(
    request_path: str, timestamp: int | None = None
) -> tuple[str, str, int]:
    now = int(timestamp if timestamp is not None else time.time())
    nonce = generate_nonce(now)
    return build_hkey(request_path, now, nonce), nonce, now


def generate_xhh_token(timestamp: int | None = None) -> str:
    now = int(timestamp if timestamp is not None else time.time())
    raw = bytearray(hashlib.md5(str(now).encode("ascii")).digest())
    for seed in TOKEN_SEEDS:
        raw.extend(hashlib.md5(seed.encode("utf-8")).digest())
    raw.append(0)
    return base64.b64encode(bytes(raw)).decode("ascii")
