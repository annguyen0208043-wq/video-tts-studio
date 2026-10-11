import pytest

from app.services.sequence_engine import SequenceLimitError, estimate_count, generate_sequences


def test_two_video_permutations():
    assert generate_sequences(["A", "B"], "permutation", 2, 100) == [("A", "B"), ("B", "A")]


def test_two_video_product_with_repetition():
    assert generate_sequences(["A", "B"], "product_with_repetition", 2, 100) == [
        ("A", "A"), ("A", "B"), ("B", "A"), ("B", "B")
    ]


def test_sequence_limit_is_checked_before_generation():
    assert estimate_count(5, "product_with_repetition", 5) == 3125
    with pytest.raises(SequenceLimitError):
        generate_sequences(["A", "B", "C", "D", "E"], "product_with_repetition", 5, 100)


def test_duplicate_source_ids_are_rejected():
    with pytest.raises(ValueError):
        generate_sequences(["A", "A"], "permutation", 2, 100)

