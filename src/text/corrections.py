"""
Correction pipeline for post-processing ASR transcriptions.
Replaces the old SubstitutionManager with a staged pipeline approach.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CorrectionRecord:
    """A single correction that was applied."""
    stage: str
    original: str
    corrected: str
    position: int = 0


@dataclass
class CorrectionResult:
    """Result of running text through correction stages."""
    text: str
    corrections: List[CorrectionRecord] = field(default_factory=list)


class CorrectionStage:
    """Base class for correction pipeline stages."""

    name: str = "base"

    def apply(self, text: str) -> CorrectionResult:
        """Apply corrections to text. Must be overridden."""
        raise NotImplementedError


class TermReplacementStage(CorrectionStage):
    """
    Replaces misheard terms with correct forms.
    Direct successor of SubstitutionManager with same data format.
    """

    name = "term_replacement"

    DEFAULT_CORRECTIONS = {
        # Command triggers - normalize variations
        "voice box": "voicebox",
        "voice-box": "voicebox",
        "voicebox": "voicebox",
        # Common tech brand names
        "superbase": "Supabase",
        "super base": "Supabase",
        "versel": "Vercel",
        "versell": "Vercel",
        "get hub": "GitHub",
        "get lab": "GitLab",
        "docker hub": "DockerHub",
        "kubernetes": "Kubernetes",
        "coobernetes": "Kubernetes",
        "python": "Python",
        "pie thon": "Python",
        "java script": "JavaScript",
        "type script": "TypeScript",
        "react": "React",
        "view": "Vue",
        "angular": "Angular",
        "next js": "Next.js",
        "next.js": "Next.js",
        "node js": "Node.js",
        "express js": "Express.js",
        "mongo db": "MongoDB",
        "postgres": "PostgreSQL",
        "my sql": "MySQL",
        "redis": "Redis",
        "elastic search": "Elasticsearch",
        "graph ql": "GraphQL",
        "rest api": "REST API",
        "json": "JSON",
        "yaml": "YAML",
        "toml": "TOML",
        "aws": "AWS",
        "gcp": "GCP",
        "azure": "Azure",
        # Common programming terms
        "a p i": "API",
        "u r l": "URL",
        "u r i": "URI",
        "h t t p": "HTTP",
        "h t t p s": "HTTPS",
        "s q l": "SQL",
        "no sql": "NoSQL",
        "crud": "CRUD",
        "rest full": "RESTful",
        "j w t": "JWT",
        "o auth": "OAuth",
        "sass": "SaaS",
        "pass": "PaaS",
        "i a a s": "IaaS",
        # Common tech terms that get mangled
        "back end": "backend",
        "front end": "frontend",
        "full stack": "fullstack",
        "dev ops": "DevOps",
        "c i c d": "CI/CD",
        "machine learning": "machine learning",
        "a i": "AI",
        "l l m": "LLM",
        "g p t": "GPT",
        # Common commands/tools
        "npm": "npm",
        "yarn": "yarn",
        "pip": "pip",
        "docker": "Docker",
        "compose": "Compose",
        "cube control": "kubectl",
        "cube c t l": "kubectl",
        "vim": "vim",
        "emacs": "Emacs",
        "v s code": "VS Code",
        "visual studio code": "VS Code",
        # Git-specific patterns
        "get push": "git push",
        "get pull": "git pull",
        "get commit": "git commit",
        "get add": "git add",
        "get status": "git status",
        "get checkout": "git checkout",
        "get branch": "git branch",
        "get merge": "git merge",
        "get clone": "git clone",
        "get init": "git init",
        "get remote": "git remote",
        "get fetch": "git fetch",
        "get diff": "git diff",
        "get log": "git log",
        "get reset": "git reset",
    }

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.corrections_file = config_dir / "corrections.json"
        self._old_substitutions_file = config_dir / "substitutions.json"
        self.corrections: Dict[str, str] = {}
        self._deleted_defaults: List[str] = []
        self._compiled_pattern: Optional[re.Pattern] = None
        self._sorted_pairs: List[Tuple[str, str]] = []

        self._migrate_if_needed()
        self.load()

    def _migrate_if_needed(self) -> None:
        """Auto-migrate from substitutions.json if corrections.json doesn't exist."""
        if not self.corrections_file.exists() and self._old_substitutions_file.exists():
            try:
                import shutil
                shutil.copy2(self._old_substitutions_file, self.corrections_file)
                logger.info("Migrated substitutions.json -> corrections.json")
            except Exception as e:
                logger.error(f"Migration failed: {e}")

    def load(self) -> None:
        """Load corrections from config file."""
        self.corrections = self.DEFAULT_CORRECTIONS.copy()
        self._deleted_defaults = []

        if self.corrections_file.exists():
            try:
                with open(self.corrections_file, "r", encoding="utf-8") as f:
                    user_data = json.load(f)

                if "_deleted" in user_data:
                    self._deleted_defaults = user_data["_deleted"]
                    for pattern in self._deleted_defaults:
                        if pattern in self.corrections:
                            del self.corrections[pattern]

                user_corrections = {
                    k: v for k, v in user_data.items() if k != "_deleted"
                }
                self.corrections.update(user_corrections)
                logger.debug(
                    f"Loaded {len(user_corrections)} user corrections, "
                    f"{len(self._deleted_defaults)} deletions"
                )
            except Exception as e:
                logger.error(f"Failed to load corrections: {e}")

        self._compile_pattern()

    def _compile_pattern(self) -> None:
        """Compile a single combined regex for all patterns (longest-first)."""
        self._sorted_pairs = sorted(
            self.corrections.items(), key=lambda x: len(x[0]), reverse=True
        )
        if self._sorted_pairs:
            alternatives = "|".join(
                r"\b" + re.escape(pattern) + r"\b"
                for pattern, _ in self._sorted_pairs
            )
            self._compiled_pattern = re.compile(alternatives, re.IGNORECASE)
        else:
            self._compiled_pattern = None

    def apply(self, text: str) -> CorrectionResult:
        """Apply term replacements to text."""
        if not text or not self._compiled_pattern:
            return CorrectionResult(text=text)

        corrections = []
        # Build a lookup dict for the replacement function
        lookup = {p.lower(): r for p, r in self._sorted_pairs}

        def replacer(match):
            original = match.group(0)
            replacement = lookup.get(original.lower(), original)
            if replacement != original:
                corrections.append(CorrectionRecord(
                    stage=self.name,
                    original=original,
                    corrected=replacement,
                    position=match.start(),
                ))
            return replacement

        result = self._compiled_pattern.sub(replacer, text)
        return CorrectionResult(text=result, corrections=corrections)

    def save(self) -> bool:
        """Save current corrections to file."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            user_corrections = {
                k: v
                for k, v in self.corrections.items()
                if k not in self.DEFAULT_CORRECTIONS
                or self.DEFAULT_CORRECTIONS[k] != v
            }
            save_data = user_corrections.copy()
            if self._deleted_defaults:
                save_data["_deleted"] = self._deleted_defaults
            with open(self.corrections_file, "w", encoding="utf-8") as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Failed to save corrections: {e}")
            return False

    def add_correction(self, pattern: str, replacement: str) -> None:
        """Add or update a correction."""
        pattern = pattern.lower()
        self.corrections[pattern] = replacement
        if pattern in self._deleted_defaults:
            self._deleted_defaults.remove(pattern)
        self.save()
        self._compile_pattern()

    def remove_correction(self, pattern: str) -> bool:
        """Remove a correction."""
        pattern = pattern.lower()
        if pattern in self.corrections:
            del self.corrections[pattern]
            if pattern in self.DEFAULT_CORRECTIONS:
                if pattern not in self._deleted_defaults:
                    self._deleted_defaults.append(pattern)
            else:
                if pattern in self._deleted_defaults:
                    self._deleted_defaults.remove(pattern)
            self.save()
            self._compile_pattern()
            return True
        return False

    def get_all_corrections(self) -> Dict[str, str]:
        """Get all current corrections."""
        return self.corrections.copy()

    def reset_to_defaults(self) -> None:
        """Reset corrections to defaults."""
        self.corrections = self.DEFAULT_CORRECTIONS.copy()
        self._deleted_defaults = []
        if self.corrections_file.exists():
            self.corrections_file.unlink()
        self._compile_pattern()

    def import_corrections(self, file_path: str) -> bool:
        """Import corrections from a JSON file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                imported = json.load(f)
            if isinstance(imported, dict):
                if "_deleted" in imported:
                    for pattern in imported["_deleted"]:
                        if pattern not in self._deleted_defaults:
                            self._deleted_defaults.append(pattern)
                    del imported["_deleted"]
                self.corrections.update(imported)
                for pattern in self._deleted_defaults:
                    if pattern in self.corrections:
                        del self.corrections[pattern]
                self.save()
                self._compile_pattern()
                return True
        except Exception as e:
            logger.error(f"Failed to import corrections: {e}")
        return False

    def export_corrections(self, file_path: str) -> bool:
        """Export corrections to a JSON file."""
        try:
            export_data = self.corrections.copy()
            if self._deleted_defaults:
                export_data["_deleted"] = self._deleted_defaults
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Failed to export corrections: {e}")
            return False


class NumberNormalizationStage(CorrectionStage):
    """Converts spoken numbers to digits when appropriate."""

    name = "number_normalization"

    # Word-to-number mappings
    _ONES = {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
        "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
        "eighteen": 18, "nineteen": 19,
    }
    _TENS = {
        "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    }
    _SCALES = {
        "hundred": 100, "thousand": 1000, "million": 1_000_000,
        "billion": 1_000_000_000,
    }

    _OPERATORS = {
        "plus": "+",
        "minus": "-",
        "times": "*",
    }

    _MULTI_WORD_OPERATORS = {
        ("multiplied", "by"): "*",
        ("divided", "by"): "/",
    }

    # Pattern to match compound numbers like "twenty three" or "four point nine"
    _NUM_WORDS = set(list(_ONES.keys()) + list(_TENS.keys()) + list(_SCALES.keys()) + ["point", "and"])

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def apply(self, text: str) -> CorrectionResult:
        if not self.enabled or not text:
            return CorrectionResult(text=text)

        corrections = []
        words = text.split()
        result_words = []
        i = 0

        while i < len(words):
            math_match = self._match_math_expression(words, i)
            if math_match is not None:
                end_idx, original, corrected = math_match
                corrections.append(CorrectionRecord(
                    stage=self.name,
                    original=original,
                    corrected=corrected,
                    position=len(" ".join(result_words)),
                ))
                result_words.append(corrected)
                i = end_idx
                continue

            # Check if this word starts a number sequence
            word_lower = words[i].lower().rstrip(".,;:!?")
            if word_lower in self._NUM_WORDS and word_lower != "and":
                # Collect consecutive number words
                num_words = []
                j = i
                while j < len(words):
                    w = words[j].lower().rstrip(".,;:!?")
                    if w in self._NUM_WORDS:
                        num_words.append(w)
                        j += 1
                    else:
                        break

                # Only convert if it's a compound (2+ words) or a decimal
                if len(num_words) >= 2:
                    original = " ".join(words[i:j])
                    number_str = self._words_to_number(num_words)
                    if number_str is not None:
                        # Preserve trailing punctuation from last word
                        trailing = ""
                        last_word = words[j - 1]
                        for ch in reversed(last_word):
                            if ch in ".,;:!?":
                                trailing = ch + trailing
                            else:
                                break

                        corrections.append(CorrectionRecord(
                            stage=self.name,
                            original=original,
                            corrected=number_str + trailing,
                            position=len(" ".join(result_words)),
                        ))
                        result_words.append(number_str + trailing)
                        i = j
                        continue

            result_words.append(words[i])
            i += 1

        return CorrectionResult(
            text=" ".join(result_words),
            corrections=corrections,
        )

    def _match_math_expression(self, words: List[str], start: int) -> Optional[Tuple[int, str, str]]:
        left = self._consume_number(words, start, allow_single=True)
        if left is None:
            return None

        left_end, left_value = left
        operator = self._consume_operator(words, left_end)
        if operator is None:
            return None

        operator_end, operator_symbol = operator
        right = self._consume_number(words, operator_end, allow_single=True)
        if right is None:
            return None

        right_end, right_value = right
        trailing = self._trailing_punctuation(words[right_end - 1])
        original = " ".join(words[start:right_end])
        return right_end, original, f"{left_value} {operator_symbol} {right_value}{trailing}"

    def _consume_operator(self, words: List[str], start: int) -> Optional[Tuple[int, str]]:
        if start >= len(words):
            return None

        first = words[start].lower().rstrip(".,;:!?")
        for phrase, symbol in self._MULTI_WORD_OPERATORS.items():
            end = start + len(phrase)
            if end <= len(words):
                candidate = tuple(w.lower().rstrip(".,;:!?") for w in words[start:end])
                if candidate == phrase:
                    return end, symbol

        if first in self._OPERATORS:
            return start + 1, self._OPERATORS[first]
        return None

    def _consume_number(self, words: List[str], start: int, allow_single: bool = False) -> Optional[Tuple[int, str]]:
        if start >= len(words):
            return None

        num_words = []
        j = start
        while j < len(words):
            w = words[j].lower().rstrip(".,;:!?")
            if w in self._NUM_WORDS:
                num_words.append(w)
                j += 1
            else:
                break

        if not num_words:
            return None
        if len(num_words) == 1 and not allow_single:
            return None

        number_str = self._words_to_number(num_words)
        if number_str is None:
            return None
        return j, number_str

    @staticmethod
    def _trailing_punctuation(word: str) -> str:
        trailing = ""
        for ch in reversed(word):
            if ch in ".,;:!?":
                trailing = ch + trailing
            else:
                break
        return trailing

    def _words_to_number(self, words: List[str]) -> Optional[str]:
        """Convert a list of number words to a digit string. Returns None on failure."""
        # Handle decimal: "four point nine" -> "4.9"
        if "point" in words:
            point_idx = words.index("point")
            integer_part = words[:point_idx]
            decimal_part = words[point_idx + 1:]

            if not integer_part or not decimal_part:
                return None

            int_val = self._parse_integer(integer_part)
            if int_val is None:
                return None

            # Decimal digits: each word is a single digit
            dec_digits = []
            for w in decimal_part:
                if w in self._ONES and self._ONES[w] <= 9:
                    dec_digits.append(str(self._ONES[w]))
                else:
                    return None
            return f"{int_val}.{''.join(dec_digits)}"

        # Pure integer
        # Treat "and" only as a connector in scaled compound numbers like
        # "one hundred and five"; do not turn "four and five" into 9.
        if "and" in words and not any(w in self._SCALES for w in words):
            return None

        # Filter out valid connector "and"
        words = [w for w in words if w != "and"]
        val = self._parse_integer(words)
        if val is not None:
            return str(val)
        return None

    def _parse_integer(self, words: List[str]) -> Optional[int]:
        """Parse a list of number words into an integer."""
        if not words:
            return None

        total = 0
        current = 0

        for word in words:
            if word in self._ONES:
                current += self._ONES[word]
            elif word in self._TENS:
                current += self._TENS[word]
            elif word == "hundred":
                if current == 0:
                    current = 1
                current *= 100
            elif word == "thousand":
                if current == 0:
                    current = 1
                total += current * 1000
                current = 0
            elif word == "million":
                if current == 0:
                    current = 1
                total += current * 1_000_000
                current = 0
            elif word == "billion":
                if current == 0:
                    current = 1
                total += current * 1_000_000_000
                current = 0
            else:
                return None

        total += current
        return total


class CorrectionPipeline:
    """Runs text through ordered correction stages."""

    def __init__(self, config_dir: Path, number_normalization_enabled: bool = True):
        self.stages: List[CorrectionStage] = [
            TermReplacementStage(config_dir),
            NumberNormalizationStage(enabled=number_normalization_enabled),
        ]

    @property
    def term_stage(self) -> TermReplacementStage:
        """Direct access to the term replacement stage."""
        return self.stages[0]

    @property
    def number_stage(self) -> NumberNormalizationStage:
        """Direct access to the number normalization stage."""
        return self.stages[1]

    def apply(self, text: str) -> CorrectionResult:
        """Run text through all correction stages."""
        if not text:
            return CorrectionResult(text=text)

        all_corrections = []
        result = text

        for stage in self.stages:
            stage_result = stage.apply(result)
            result = stage_result.text
            all_corrections.extend(stage_result.corrections)

        return CorrectionResult(text=result, corrections=all_corrections)

    def reload(self) -> None:
        """Reload correction data from disk."""
        for stage in self.stages:
            if hasattr(stage, "load"):
                stage.load()
