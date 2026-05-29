"""Tests for VoiceBox text correction stages."""

from src.text.corrections import NumberNormalizationStage


def normalize_numbers(text: str) -> str:
    return NumberNormalizationStage().apply(text).text


def test_number_normalization_does_not_treat_and_as_addition():
    assert normalize_numbers("four and five") == "four and five"
    assert normalize_numbers("I need four and five examples") == "I need four and five examples"


def test_number_normalization_keeps_compound_and_connector():
    assert normalize_numbers("one hundred and five") == "105"
    assert normalize_numbers("two thousand and six") == "2006"


def test_number_normalization_converts_explicit_spoken_math_to_symbols():
    assert normalize_numbers("four plus five") == "4 + 5"
    assert normalize_numbers("twenty three minus seven") == "23 - 7"
    assert normalize_numbers("six times nine") == "6 * 9"
    assert normalize_numbers("eight divided by two") == "8 / 2"


def test_number_normalization_preserves_spoken_math_punctuation():
    assert normalize_numbers("what is four plus five?") == "what is 4 + 5?"
