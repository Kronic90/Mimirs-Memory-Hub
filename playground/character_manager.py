"""Character management for Mimir's Memory Hub."""
from __future__ import annotations
import json
import uuid
from pathlib import Path
from typing import Optional, Any

_DATA_DIR = Path(__file__).resolve().parent.parent / "playground_data"


class CharacterManager:
    """Manage character files and metadata."""

    def __init__(self):
        self.chars_dir = _DATA_DIR / "characters"
        self.chars_dir.mkdir(parents=True, exist_ok=True)

    def list_characters(self) -> list[dict]:
        """List all characters with full data."""
        chars = []
        for char_file in self.chars_dir.glob("*.json"):
            try:
                with open(char_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data.setdefault("id", char_file.stem)
                data.setdefault("path", str(char_file))
                chars.append(data)
            except Exception:
                pass
        return chars

    def get_character(self, char_id: str) -> Optional[dict]:
        """Load a character by ID."""
        char_file = self.chars_dir / f"{char_id}.json"
        if not char_file.exists():
            return None
        try:
            with open(char_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def get_memory_dir(self, char_id: str, profile_dir: Path) -> Path:
        """Return the isolated memory directory for a character."""
        d = profile_dir / "characters" / char_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def create_character(self, name: str, description: str = "", **kwargs) -> dict:
        """Create a new character."""
        char_id = str(uuid.uuid4())[:8]
        char_data = {
            "id": char_id,
            "name": name,
            "description": description,
            "greeting": kwargs.get("greeting", ""),
            "scenario": kwargs.get("scenario", ""),
            "personality": kwargs.get("personality", ""),
            "system_prompt": kwargs.get("system_prompt", ""),
            "voice_prompt": kwargs.get("voice_prompt", ""),
            "preset_type": kwargs.get("preset_type", "companion"),
            "model": kwargs.get("model", ""),
            "backend": kwargs.get("backend", ""),
            "tts_voice": kwargs.get("tts_voice", ""),
            "alternate_greetings": kwargs.get("alternate_greetings", []),
            "_created": int(__import__("time").time()),
            "_source": "manual",
        }
        char_data.update(kwargs)
        
        char_file = self.chars_dir / f"{char_id}.json"
        with open(char_file, "w", encoding="utf-8") as f:
            json.dump(char_data, f, indent=2)
        
        return char_data

    def update_character(self, char_id: str, updates: dict) -> Optional[dict]:
        """Update character data."""
        char = self.get_character(char_id)
        if not char:
            return None
        char.update(updates)
        char_file = self.chars_dir / f"{char_id}.json"
        with open(char_file, "w", encoding="utf-8") as f:
            json.dump(char, f, indent=2)
        return char

    def delete_character(self, char_id: str) -> bool:
        """Delete a character."""
        char_file = self.chars_dir / f"{char_id}.json"
        if char_file.exists():
            char_file.unlink()
            return True
        return False

    def import_sillytavern(self, file_path: str) -> dict:
        """Import a SillyTavern character (.json or .character format)."""
        import_file = Path(file_path)
        if not import_file.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        try:
            with open(import_file, "r", encoding="utf-8") as f:
                st_data = json.load(f)
        except Exception as e:
            raise ValueError(f"Invalid JSON file: {e}")
        
        # SillyTavern format variations
        name = st_data.get("char_name") or st_data.get("name") or "Imported Character"
        description = st_data.get("description", "")
        
        # Create character with ST data preserved
        char_id = str(uuid.uuid4())[:8]
        char_data = {
            "id": char_id,
            "name": name,
            "description": description,
            "greeting": st_data.get("first_mes", ""),
            "scenario": st_data.get("scenario", ""),
            "personality": st_data.get("personality", ""),
            "system_prompt": st_data.get("system_prompt", "") or st_data.get("mes_example", ""),
            "voice_prompt": "",
            "alternate_greetings": st_data.get("alternate_greetings", []),
            "_created": int(__import__("time").time()),
            "_source": "sillytavern",
            "_original": st_data,  # Store original for round-trip if needed
        }
        
        char_file = self.chars_dir / f"{char_id}.json"
        with open(char_file, "w", encoding="utf-8") as f:
            json.dump(char_data, f, indent=2)
        
        return char_data

    def bulk_import_folder(self, folder_path: str) -> dict:
        """Bulk import all SillyTavern characters from a folder."""
        folder = Path(folder_path)
        if not folder.is_dir():
            raise NotADirectoryError(f"Not a directory: {folder_path}")

        imported = []
        errors = []
        
        # Look for .json and .character files
        for pattern in ["*.json", "*.character"]:
            for file_path in folder.glob(pattern):
                # Skip non-character JSON files (e.g., settings.json, metadata.json)
                if file_path.name.lower() in ("settings.json", "metadata.json", "config.json"):
                    continue

                try:
                    char = self.import_sillytavern(str(file_path))
                    imported.append({
                        "name": char["name"],
                        "id": char["id"],
                        "file": file_path.name,
                    })
                except Exception as e:
                    errors.append({
                        "file": file_path.name,
                        "error": str(e),
                    })

        return {
            "imported": imported,
            "errors": errors,
            "total": len(imported),
            "failed": len(errors),
        }
