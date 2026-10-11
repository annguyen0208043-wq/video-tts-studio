from __future__ import annotations

import itertools
import math


class SequenceLimitError(ValueError):
    pass


def estimate_count(item_count: int, mode: str, length: int | None = None) -> int:
    if item_count < 1:
        return 0
    if mode == "manual":
        return 1
    k = length or item_count
    if mode == "permutation":
        if k > item_count:
            return 0
        return math.factorial(item_count) // math.factorial(item_count - k)
    if mode == "product_with_repetition":
        return item_count**k
    raise ValueError("Chế độ sequence không hợp lệ")


def generate_sequences(
    asset_ids: list[str], mode: str, length: int | None, limit: int
) -> list[tuple[str, ...]]:
    if not asset_ids:
        raise ValueError("Cần ít nhất một video")
    if len(set(asset_ids)) != len(asset_ids):
        raise ValueError("Danh sách nguồn không được chứa ID trùng")
    count = estimate_count(len(asset_ids), mode, length)
    if count > limit:
        raise SequenceLimitError(f"Sẽ tạo {count} chuỗi, vượt giới hạn {limit}")
    k = length or len(asset_ids)
    if mode == "permutation":
        return list(itertools.permutations(asset_ids, k))
    if mode == "product_with_repetition":
        return list(itertools.product(asset_ids, repeat=k))
    raise ValueError("Chế độ sequence không hợp lệ")

