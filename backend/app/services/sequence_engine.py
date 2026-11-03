from __future__ import annotations

class SequenceLimitError(ValueError):
    pass


def estimate_count(item_count: int, mode: str, length: int | None = None) -> int:
    if mode == "single_self_repeat":
        return 1 if item_count == 1 else 0
    if item_count != 2:
        return 0
    if mode == "pair_once":
        return 1
    if mode == "pair_both_orders":
        return 2
    if mode == "pair_self_repeats":
        return 2
    raise ValueError("Chế độ sequence không hợp lệ")


def generate_sequences(
    asset_ids: list[str], mode: str, length: int | None, limit: int
) -> list[tuple[str, ...]]:
    required_count = 1 if mode == "single_self_repeat" else 2
    if len(asset_ids) != required_count:
        raise ValueError(f"Cần chọn đúng {required_count} video")
    if len(set(asset_ids)) != len(asset_ids):
        raise ValueError("Danh sách nguồn không được chứa ID trùng")
    count = estimate_count(len(asset_ids), mode, length)
    if count > limit:
        raise SequenceLimitError(f"Sẽ tạo {count} chuỗi, vượt giới hạn {limit}")
    first = asset_ids[0]
    if mode == "single_self_repeat":
        return [(first, first)]
    second = asset_ids[1]
    if mode == "pair_once":
        return [(first, second)]
    if mode == "pair_both_orders":
        return [(first, second), (second, first)]
    if mode == "pair_self_repeats":
        return [(first, first), (second, second)]
    raise ValueError("Chế độ sequence không hợp lệ")

