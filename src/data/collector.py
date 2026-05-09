"""
Training data collection for future ASR fine-tuning.
Saves audio + transcription pairs in an append-only JSONL manifest.
"""

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.logging import get_logger

logger = get_logger(__name__)


class TrainingDataCollector:
    """Collects audio + transcription pairs for future fine-tuning."""

    def __init__(self, config_dir: Path, max_mb: int = 2048, enabled: bool = True):
        self.enabled = enabled
        self.max_bytes = max_mb * 1024 * 1024
        self.data_dir = config_dir / "training_data"
        self.audio_dir = self.data_dir / "audio"
        self.index_file = self.data_dir / "index.jsonl"

        if self.enabled:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.audio_dir.mkdir(parents=True, exist_ok=True)

    def save_sample(
        self,
        audio_file: str,
        raw_transcript: str,
        auto_corrected: str,
        corrections_applied: Optional[List[Dict[str, Any]]] = None,
        was_command: bool = False,
    ) -> Optional[str]:
        """
        Save a training sample. Copies audio and appends to index.

        Returns the sample ID, or None if saving failed or disabled.
        """
        if not self.enabled:
            return None

        try:
            source = Path(audio_file)
            if not source.exists():
                logger.warning(f"Audio file not found for training data: {audio_file}")
                return None

            # Generate ID
            ts = datetime.now(timezone.utc)
            sample_id = ts.strftime("%Y-%m-%d_%H%M%S") + f"_{id(audio_file) % 0xFFFF:04x}"

            # Copy audio
            dest_name = f"{sample_id}{source.suffix}"
            dest_path = self.audio_dir / dest_name
            shutil.copy2(source, dest_path)

            # Get audio duration (approximate from file size at 16kHz mono 16-bit)
            audio_bytes = dest_path.stat().st_size
            duration_sec = round(audio_bytes / (16000 * 2), 1)  # 16kHz, 16-bit

            # Build record
            record = {
                "id": sample_id,
                "timestamp": ts.isoformat(),
                "audio_file": f"audio/{dest_name}",
                "audio_duration_sec": duration_sec,
                "raw_transcript": raw_transcript,
                "auto_corrected": auto_corrected,
                "user_corrected": None,
                "corrections_applied": corrections_applied or [],
                "user_edited": False,
                "was_command": was_command,
            }

            # Append to index
            with open(self.index_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

            logger.debug(f"Saved training sample: {sample_id}")

            # Prune if over limit
            self._prune_if_needed()

            return sample_id

        except Exception as e:
            logger.error(f"Failed to save training sample: {e}")
            return None

    def update_sample(self, sample_id: str, user_corrected: str) -> bool:
        """Update a sample with user correction."""
        if not self.enabled or not self.index_file.exists():
            return False

        try:
            lines = self.index_file.read_text(encoding="utf-8").splitlines()
            updated = False

            with open(self.index_file, "w", encoding="utf-8") as f:
                for line in lines:
                    if not line.strip():
                        continue
                    record = json.loads(line)
                    if record.get("id") == sample_id:
                        record["user_corrected"] = user_corrected
                        record["user_edited"] = True
                        updated = True
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

            return updated
        except Exception as e:
            logger.error(f"Failed to update training sample: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about collected training data."""
        stats = {
            "total_samples": 0,
            "user_edited": 0,
            "commands": 0,
            "total_audio_duration_sec": 0.0,
            "total_size_mb": 0.0,
        }

        if not self.index_file.exists():
            return stats

        try:
            for line in self.index_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                stats["total_samples"] += 1
                if record.get("user_edited"):
                    stats["user_edited"] += 1
                if record.get("was_command"):
                    stats["commands"] += 1
                stats["total_audio_duration_sec"] += record.get("audio_duration_sec", 0)

            # Calculate disk usage
            if self.data_dir.exists():
                total_bytes = sum(
                    f.stat().st_size for f in self.data_dir.rglob("*") if f.is_file()
                )
                stats["total_size_mb"] = round(total_bytes / (1024 * 1024), 1)

        except Exception as e:
            logger.error(f"Failed to get training data stats: {e}")

        return stats

    def export(self, output_dir: str) -> bool:
        """Export all training data to a directory."""
        try:
            dest = Path(output_dir)
            if self.data_dir.exists():
                shutil.copytree(self.data_dir, dest, dirs_exist_ok=True)
                return True
        except Exception as e:
            logger.error(f"Failed to export training data: {e}")
        return False

    def clear(self) -> None:
        """Delete all training data."""
        try:
            if self.data_dir.exists():
                shutil.rmtree(self.data_dir)
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.audio_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Training data cleared")
        except Exception as e:
            logger.error(f"Failed to clear training data: {e}")

    def _prune_if_needed(self) -> None:
        """Remove oldest samples if total size exceeds limit (FIFO)."""
        if not self.data_dir.exists():
            return

        try:
            total_bytes = sum(
                f.stat().st_size for f in self.data_dir.rglob("*") if f.is_file()
            )
            if total_bytes <= self.max_bytes:
                return

            # Read all records
            if not self.index_file.exists():
                return
            lines = self.index_file.read_text(encoding="utf-8").splitlines()
            records = [json.loads(l) for l in lines if l.strip()]

            # Remove oldest until under limit
            removed = 0
            while records and total_bytes > self.max_bytes:
                oldest = records.pop(0)
                audio_path = self.data_dir / oldest.get("audio_file", "")
                if audio_path.exists():
                    total_bytes -= audio_path.stat().st_size
                    audio_path.unlink()
                removed += 1

            # Rewrite index
            with open(self.index_file, "w", encoding="utf-8") as f:
                for record in records:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

            if removed:
                logger.info(f"Pruned {removed} old training samples")

        except Exception as e:
            logger.error(f"Failed to prune training data: {e}")
