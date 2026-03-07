from __future__ import annotations

import re
from hashlib import sha256
from math import sqrt


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")
DEFAULT_EMBEDDING_DIMENSION = 64


def build_text_embedding(text: str, dimensions: int = DEFAULT_EMBEDDING_DIMENSION) -> list[float]:
    if dimensions <= 0:
        raise ValueError("embedding dimensions must be positive")
    vector = [0.0] * dimensions
    tokens = TOKEN_PATTERN.findall(text.lower())
    if not tokens:
        tokens = [character for character in text.strip() if not character.isspace()]
    for token in tokens:
        digest = sha256(token.encode("utf-8")).digest()
        for offset in range(4):
            index = int.from_bytes(digest[offset * 2 : offset * 2 + 2], "big") % dimensions
            sign = 1.0 if digest[16 + offset] % 2 == 0 else -1.0
            vector[index] += sign
    return normalize_embedding(vector)


def normalize_embedding(vector: list[float]) -> list[float]:
    norm = sqrt(sum(value * value for value in vector))
    if norm == 0:
        return [0.0 for _ in vector]
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(left[index] * right[index] for index in range(len(left)))
