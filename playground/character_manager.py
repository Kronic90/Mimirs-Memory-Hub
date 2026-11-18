"""Character management for Mimir's Memory Hub."""
from __future__ import annotations
import json
import shutil
import uuid
from pathlib import Path
from typing import Optional, Any

_DATA_DIR = Path(__file__).resolve().parent.parent / "playground_data"


class CharacterManager:
    """Manage character files and metadata."""

    def __init__(self):
        self.chars_dir = _DATA_DIR / "characters"
        self.chars_dir.mkdir(parents=True, exist_ok=True)
        self.avatars_dir = self.chars_dir / "avatars"

    # ── Pictures ───────────────────────────────────────────────────────
    def avatar_path(self, char_id: str) -> Path | None:
        p = self.avatars_dir / f"{char_id}.webp"
        return p if p.is_file() else None

    def save_avatar(self, char_id: str, image_bytes: bytes) -> dict | None:
        """Store a character picture (any common format), square-cropped
        around the top-centre (where faces usually are) to 512px WebP."""
        if not self.get_character(char_id):
            return None
        from PIL import Image, ImageOps
        import io, time
        img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(img).convert("RGBA")
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top = 0 if h > w else (h - side) // 2   # portraits: keep the head
        img = img.crop((left, top, left + side, top + side)).resize((512, 512), Image.LANCZOS)
        bg = Image.new("RGB", img.size, (24, 24, 32))
        bg.paste(img, mask=img.split()[-1])
        self.avatars_dir.mkdir(parents=True, exist_ok=True)
        bg.save(self.avatars_dir / f"{char_id}.webp", format="WEBP", quality=88)
        return self.update_character(char_id, {"avatar": int(time.time())})

    def remove_avatar(self, char_id: str) -> dict | None:
        p = self.avatar_path(char_id)
        if p:
            p.unlink()
        return self.update_character(char_id, {"avatar": 0})

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

    def delete_character(self, char_id: str, profile_dir: Path | None = None) -> bool:
        """Delete a character, along with its isolated memory directory
        (if profile_dir is given) so memories don't get orphaned on disk."""
        char_file = self.chars_dir / f"{char_id}.json"
        if not char_file.exists():
            return False
        char_file.unlink()
        av = self.avatar_path(char_id)
        if av:
            av.unlink()
        if profile_dir is not None:
            mem_dir = profile_dir / "characters" / char_id
            shutil.rmtree(mem_dir, ignore_errors=True)
        return True

    def import_card_bytes(self, filename: str, data: bytes) -> dict:
        """Import a character from an uploaded file: a SillyTavern/Tavern/
        Chub card PNG (picture becomes the avatar) or a card JSON."""
        from playground.character_sheet import read_card_png, card_to_character
        from playground import cof_import
        if cof_import.is_cof(data):
            return self.import_cof(data)[0]
        is_png = data[:8] == b"\x89PNG\r\n\x1a\n"
        if is_png:
            card = read_card_png(data)
        else:
            try:
                card = json.loads(data.decode("utf-8-sig"))
            except Exception as e:
                raise ValueError(f"Not a character card (PNG or JSON): {e}")
            if not isinstance(card, dict):
                raise ValueError("Not a character card (expected a JSON object)")
        fields = card_to_character(card)
        char = self.create_character(fields.pop("name"), fields.pop("description", ""),
                                     **fields)
        src = "character.ai" if fields.get("_cai") else ("card-png" if is_png else "card-json")
        char = self.update_character(char["id"], {"_source": src}) or char
        if is_png:
            try:
                char = self.save_avatar(char["id"], data) or char
            except Exception:
                pass
        return char

    def import_cof(self, data: bytes, include_secret: bool = False) -> tuple[dict, dict]:
        """Import a character from a COF file (.cof): its card (or free-text
        personality) becomes the sheet, its thumbnail the picture. Returns
        (character, parsed); parsed["memories"] is for the caller to hand to
        that character's memory, as the Character.ai import does."""
        from playground import cof_import
        from playground.character_sheet import card_to_character
        parsed = cof_import.read_cof(data, include_secret=include_secret)
        if parsed["card"]:
            fields = card_to_character(parsed["card"])
            char = self.create_character(fields.pop("name"), fields.pop("description", ""),
                                         **fields)
        else:
            char = self.create_character(parsed["name"], parsed["description"],
                                         greeting=parsed["greeting"])
        char = self.update_character(char["id"], {"_source": "cof"}) or char
        if parsed["avatar_png"]:
            try:
                char = self.save_avatar(char["id"], parsed["avatar_png"]) or char
            except Exception:
                pass
        return char, parsed

    def import_sillytavern(self, file_path: str) -> dict:
        """Import a SillyTavern character (.json or .character format)."""
        import_file = Path(file_path)
        if not import_file.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if import_file.suffix.lower() == ".png":
            return self.import_card_bytes(import_file.name, import_file.read_bytes())
        try:
            with open(import_file, "r", encoding="utf-8-sig") as f:
                st_data = json.load(f)
        except Exception as e:
            raise ValueError(f"Invalid JSON file: {e}")
        if isinstance(st_data, dict) and (st_data.get("spec") or isinstance(st_data.get("data"), dict)):
            return self.import_card_bytes(import_file.name, import_file.read_bytes())
        
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
        for pattern in ["*.json", "*.character", "*.png"]:
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
