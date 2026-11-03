import pytest

from app.services.sequence_engine import SequenceLimitError, estimate_count, generate_sequences


def test_two_video_pair_once():
    assert generate_sequences(["A", "B"], "pair_once", 2, 2) == [("A", "B")]


def test_one_video_self_repeat():
    assert estimate_count(1, "single_self_repeat", 2) == 1
    assert estimate_count(2, "single_self_repeat", 2) == 0
    assert generate_sequences(["A"], "single_self_repeat", 2, 1) == [("A", "A")]


def test_two_video_pair_both_orders():
    assert generate_sequences(["A", "B"], "pair_both_orders", 2, 2) == [("A", "B"), ("B", "A")]


def test_two_video_pair_self_repeats():
    assert estimate_count(2, "pair_self_repeats", 2) == 2
    assert generate_sequences(["A", "B"], "pair_self_repeats", 2, 2) == [("A", "A"), ("B", "B")]


def test_pair_self_repeats_respects_output_limit():
    with pytest.raises(SequenceLimitError):
        generate_sequences(["A", "B"], "pair_self_repeats", 2, 1)


def test_requires_exactly_two_videos():
    assert estimate_count(1, "pair_once", 2) == 0
    with pytest.raises(ValueError, match="đúng 2 video"):
        generate_sequences(["A"], "pair_once", 2, 2)


def test_single_self_repeat_requires_exactly_one_video():
    with pytest.raises(ValueError, match="đúng 1 video"):
        generate_sequences(["A", "B"], "single_self_repeat", 2, 2)


def test_duplicate_source_ids_are_rejected():
    with pytest.raises(ValueError):
        generate_sequences(["A", "A"], "pair_once", 2, 2)

