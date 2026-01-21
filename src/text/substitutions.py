#!/usr/bin/env python3
"""
Text substitution system for fixing common transcription errors.
Handles technical terms, brand names, and user-defined replacements.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple


class SubstitutionManager:
    """Manages text substitutions for transcribed text."""

    DEFAULT_SUBSTITUTIONS = {
        # Command triggers - normalize variations
        "voice box": "voicebox",
        "voice-box": "voicebox",
        "voicebox": "voicebox",  # Keep as-is
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
        # Git-specific patterns (only replace get with git when followed by git commands)
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

    def __init__(self, config_dir: Path = None):
        """Initialize the substitution manager."""
        if config_dir is None:
            config_dir = self._get_default_config_dir()

        self.config_dir = config_dir
        self.substitutions_file = config_dir / "substitutions.json"
        self.substitutions: Dict[str, str] = {}
        self._deleted_defaults: List[str] = []

        self.load_substitutions()

    def _get_default_config_dir(self) -> Path:
        """Get the default configuration directory."""
        import os

        if os.name == "nt":  # Windows
            base_dir = os.getenv("APPDATA", os.path.expanduser("~"))
        elif os.name == "posix":  # macOS and Linux
            if "darwin" in os.sys.platform.lower():  # macOS
                base_dir = os.path.expanduser("~/Library/Application Support")
            else:  # Linux
                base_dir = os.getenv("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        else:
            base_dir = os.path.expanduser("~")

        return Path(base_dir) / "VoiceBox"

    def load_substitutions(self) -> None:
        """Load substitutions from config file."""
        # Start with defaults
        self.substitutions = self.DEFAULT_SUBSTITUTIONS.copy()
        self._deleted_defaults = []

        # Load user substitutions if file exists
        if self.substitutions_file.exists():
            try:
                with open(self.substitutions_file, "r", encoding="utf-8") as f:
                    user_data = json.load(f)

                # Extract deleted defaults list (stored under special key)
                if "_deleted" in user_data:
                    self._deleted_defaults = user_data["_deleted"]
                    # Apply deletions
                    for pattern in self._deleted_defaults:
                        if pattern in self.substitutions:
                            del self.substitutions[pattern]

                # Extract and apply user substitutions (excluding special key)
                user_substitutions = {
                    k: v for k, v in user_data.items() if k != "_deleted"
                }
                # User substitutions override defaults
                self.substitutions.update(user_substitutions)

                print(
                    f"Loaded {len(user_substitutions)} user substitutions, {len(self._deleted_defaults)} deletions"
                )
            except Exception as e:
                print(f"Failed to load substitutions: {e}")

    def save_substitutions(self) -> bool:
        """Save current substitutions to file."""
        try:
            # Ensure config directory exists
            self.config_dir.mkdir(parents=True, exist_ok=True)

            # Save only user-modified substitutions (different from defaults)
            user_substitutions = {
                k: v
                for k, v in self.substitutions.items()
                if k not in self.DEFAULT_SUBSTITUTIONS
                or self.DEFAULT_SUBSTITUTIONS[k] != v
            }

            # Create data structure to save (may include deletions)
            save_data = user_substitutions.copy()

            # Add deleted defaults list to save file
            if self._deleted_defaults:
                save_data["_deleted"] = self._deleted_defaults

            with open(self.substitutions_file, "w", encoding="utf-8") as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Failed to save substitutions: {e}")
            return False

    def apply_substitutions(self, text: str) -> str:
        """
        Apply all substitutions to the transcribed text.

        Args:
            text: The original transcribed text

        Returns:
            Text with substitutions applied
        """
        if not text:
            return text

        result = text

        # Sort substitutions by length (longest first) to handle overlapping patterns
        sorted_subs = sorted(
            self.substitutions.items(), key=lambda x: len(x[0]), reverse=True
        )

        for pattern, replacement in sorted_subs:
            # Case-insensitive replacement with word boundaries
            # This prevents partial word replacements
            regex_pattern = r"\b" + re.escape(pattern) + r"\b"
            result = re.sub(regex_pattern, replacement, result, flags=re.IGNORECASE)

        return result

    def add_substitution(self, pattern: str, replacement: str) -> None:
        """Add or update a substitution."""
        # Convert to lowercase for the pattern
        pattern = pattern.lower()
        self.substitutions[pattern] = replacement

        # Remove from deletion list if this was a deleted default
        if pattern in self._deleted_defaults:
            self._deleted_defaults.remove(pattern)

        self.save_substitutions()

    def remove_substitution(self, pattern: str) -> bool:
        """Remove a substitution."""
        pattern = pattern.lower()
        if pattern in self.substitutions:
            del self.substitutions[pattern]
            # Track if this was a default substitution
            if pattern in self.DEFAULT_SUBSTITUTIONS:
                if pattern not in self._deleted_defaults:
                    self._deleted_defaults.append(pattern)
            else:
                # If it was a user substitution, remove from deletion list
                # (in case it was previously a default that got deleted and re-added)
                if pattern in self._deleted_defaults:
                    self._deleted_defaults.remove(pattern)
            self.save_substitutions()
            return True
        return False

    def get_all_substitutions(self) -> Dict[str, str]:
        """Get all current substitutions."""
        return self.substitutions.copy()

    def reset_to_defaults(self) -> None:
        """Reset substitutions to defaults."""
        self.substitutions = self.DEFAULT_SUBSTITUTIONS.copy()
        self._deleted_defaults = []
        # Delete user substitutions file
        if self.substitutions_file.exists():
            self.substitutions_file.unlink()

    def import_substitutions(self, file_path: str) -> bool:
        """Import substitutions from a JSON file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                imported = json.load(f)

            if isinstance(imported, dict):
                # Extract deletions if present
                if "_deleted" in imported:
                    for pattern in imported["_deleted"]:
                        if pattern not in self._deleted_defaults:
                            self._deleted_defaults.append(pattern)
                    del imported["_deleted"]

                # Import substitutions
                self.substitutions.update(imported)

                # Apply deletions
                for pattern in self._deleted_defaults:
                    if pattern in self.substitutions:
                        del self.substitutions[pattern]

                self.save_substitutions()
                return True
        except Exception as e:
            print(f"Failed to import substitutions: {e}")
        return False

    def export_substitutions(self, file_path: str) -> bool:
        """Export substitutions to a JSON file."""
        try:
            # Export with deletions included
            export_data = self.substitutions.copy()
            if self._deleted_defaults:
                export_data["_deleted"] = self._deleted_defaults

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Failed to export substitutions: {e}")
            return False


# Example usage
if __name__ == "__main__":
    manager = SubstitutionManager()

    # Test some substitutions
    test_text = "I'm using superbase with versel to build my next js app"
    result = manager.apply_substitutions(test_text)
    print(f"Original: {test_text}")
    print(f"Fixed:    {result}")

    # Add custom substitution
    manager.add_substitution("my company", "Anthropic")
    test_text2 = "I work at my company on a i models"
    result2 = manager.apply_substitutions(test_text2)
    print(f"\nOriginal: {test_text2}")
    print(f"Fixed:    {result2}")
