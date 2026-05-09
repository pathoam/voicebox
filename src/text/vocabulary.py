"""
Vocabulary biasing for ASR context.
Manages user-defined terms that bias Qwen3-ASR's decoder toward specific words.
"""

from pathlib import Path
from typing import List, Optional, Callable

from src.utils.logging import get_logger

logger = get_logger(__name__)


class VocabularyManager:
    """Manages vocabulary terms for ASR context biasing."""

    def __init__(self, config_dir: Path, default_terms: Optional[List[str]] = None):
        self.config_dir = config_dir
        self.vocabulary_file = config_dir / "vocabulary.txt"
        self._terms: List[str] = []
        self._default_terms: List[str] = default_terms or []
        self._context_string: Optional[str] = None
        self._on_change_callbacks: List[Callable[[str], None]] = []
        self.load()

    def load(self) -> None:
        """Load vocabulary terms from file."""
        self._terms = []
        if self.vocabulary_file.exists():
            try:
                text = self.vocabulary_file.read_text(encoding="utf-8")
                for line in text.splitlines():
                    term = line.strip()
                    if term:
                        self._terms.append(term)
                logger.info(f"Loaded {len(self._terms)} vocabulary terms")
            except Exception as e:
                logger.error(f"Failed to load vocabulary: {e}")
        self._rebuild_context()

    def save(self) -> bool:
        """Save vocabulary terms to file."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.vocabulary_file.write_text(
                "\n".join(self._terms) + "\n" if self._terms else "",
                encoding="utf-8",
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save vocabulary: {e}")
            return False

    def add_term(self, term: str) -> bool:
        """Add a term to the vocabulary. Returns True if added (not duplicate)."""
        term = term.strip()
        if not term:
            return False
        # Case-insensitive duplicate check
        if any(t.lower() == term.lower() for t in self._terms):
            return False
        self._terms.append(term)
        self.save()
        self._rebuild_context()
        self._notify_change()
        return True

    def remove_term(self, term: str) -> bool:
        """Remove a term from the vocabulary. Returns True if found and removed."""
        term_lower = term.strip().lower()
        for i, t in enumerate(self._terms):
            if t.lower() == term_lower:
                self._terms.pop(i)
                self.save()
                self._rebuild_context()
                self._notify_change()
                return True
        return False

    def clear(self) -> None:
        """Remove all vocabulary terms."""
        self._terms = []
        self.save()
        self._rebuild_context()
        self._notify_change()

    def get_terms(self) -> List[str]:
        """Return a copy of the current vocabulary terms."""
        return self._terms.copy()

    def get_context_string(self) -> Optional[str]:
        """Return the context string for ASR biasing, or None if empty."""
        return self._context_string

    def on_change(self, callback: Callable[[str], None]) -> None:
        """Register a callback for when vocabulary changes. Callback receives new context string."""
        self._on_change_callbacks.append(callback)

    def set_default_terms(self, terms: List[str]) -> None:
        """Update the default terms (e.g. command trigger words) and rebuild context."""
        self._default_terms = terms
        self._rebuild_context()
        self._notify_change()

    def _rebuild_context(self) -> None:
        """Rebuild the context string from current terms (including defaults)."""
        all_terms = list(self._default_terms)
        seen = {t.lower() for t in all_terms}
        for t in self._terms:
            if t.lower() not in seen:
                all_terms.append(t)
                seen.add(t.lower())
        if all_terms:
            terms_str = ", ".join(all_terms)
            self._context_string = f"The following terms may appear in the audio: {terms_str}."
        else:
            self._context_string = None

    def _notify_change(self) -> None:
        """Notify registered callbacks of vocabulary change."""
        context = self._context_string
        for cb in self._on_change_callbacks:
            try:
                cb(context)
            except Exception as e:
                logger.error(f"Vocabulary change callback error: {e}")
