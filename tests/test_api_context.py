"""Tests for ASR context parsing used by the API."""

from src.api.server import _context_from_terms, _parse_context_terms, _resolve_context


def test_context_from_terms_filters_empty_values():
    assert (
        _context_from_terms([" Optagon ", "", "Voicebox"])
        == "The following terms may appear in the audio: Optagon, Voicebox."
    )


def test_parse_context_terms_accepts_json_and_csv():
    assert _parse_context_terms('["Qwen", "ASR"]') == ["Qwen", "ASR"]
    assert _parse_context_terms("Qwen, ASR") == ["Qwen", "ASR"]


def test_resolve_context_merges_explicit_context_and_terms():
    assert (
        _resolve_context(" custom prompt ", ["Optagon", "Voicebox"])
        == "custom prompt\n\nThe following terms may appear in the audio: Optagon, Voicebox."
    )
    assert _resolve_context(None, ["Qwen"]) == "The following terms may appear in the audio: Qwen."
    assert _resolve_context(" custom prompt ", None) == "custom prompt"
