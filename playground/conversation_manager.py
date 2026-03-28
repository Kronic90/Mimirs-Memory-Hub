"""Conversation management for multi-agent chats."""
from __future__ import annotations
import json
import uuid
from pathlib import Path
from typing import Optional, Any
from datetime import datetime

_DATA_DIR = Path(__file__).resolve().parent.parent / "playground_data"


class ConversationManager:
    """Manage conversation files and history."""

    def __init__(self):
        self.convs_dir = _DATA_DIR / "conversations"
        self.convs_dir.mkdir(parents=True, exist_ok=True)

    def list_conversations(self) -> list[dict]:
        """List all conversations with metadata."""
        convs = []
        for conv_dir in self.convs_dir.iterdir():
            if not conv_dir.is_dir():
                continue
            meta_file = conv_dir / "meta.json"
            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    convs.append(meta)
                except Exception:
                    pass
        # Sort by last_modified descending
        return sorted(convs, key=lambda x: x.get("last_modified", 0), reverse=True)

    def get_conversation(self, conv_id: str) -> Optional[dict]:
        """Load full conversation."""
        conv_dir = self.convs_dir / conv_id
        meta_file = conv_dir / "meta.json"
        history_file = conv_dir / "chat_history.json"
        
        if not meta_file.exists():
            return None
        
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            
            messages = []
            if history_file.exists():
                with open(history_file, "r", encoding="utf-8") as f:
                    messages = json.load(f)
            
            return {
                "meta": meta,
                "messages": messages,
            }
        except Exception as e:
            print(f"Error loading conversation {conv_id}: {e}")
            return None

    def create_conversation(self, title: str, participants: list[dict]) -> dict:
        """Create a new conversation."""
        conv_id = str(uuid.uuid4())[:12]
        conv_dir = self.convs_dir / conv_id
        conv_dir.mkdir(parents=True, exist_ok=True)

        now = int(__import__("time").time())
        meta = {
            "id": conv_id,
            "title": title,
            "created": now,
            "last_modified": now,
            "participants": participants,  # [{"type": "user|agent", "name": str, "character_id": str}]
            "tags": [],
            "turn_limit": None,  # User can set this
            "turn_order": "user_addresses",  # Default: user addresses agents
        }

        meta_file = conv_dir / "meta.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        # Create empty history
        history_file = conv_dir / "chat_history.json"
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump([], f)

        # Create data dir for agent memories
        (conv_dir / "data").mkdir(exist_ok=True)

        return meta

    def add_message(self, conv_id: str, message: dict) -> bool:
        """Add a message to conversation history."""
        conv_dir = self.convs_dir / conv_id
        history_file = conv_dir / "chat_history.json"

        if not history_file.exists():
            return False

        try:
            with open(history_file, "r", encoding="utf-8") as f:
                messages = json.load(f)
            
            # Ensure message has turn number
            if "turn" not in message:
                message["turn"] = len(messages) + 1
            
            if "timestamp" not in message:
                message["timestamp"] = int(__import__("time").time())

            messages.append(message)

            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(messages, f)

            # Update last_modified in meta
            meta_file = conv_dir / "meta.json"
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            
            meta["last_modified"] = int(__import__("time").time())

            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)

            return True
        except Exception as e:
            print(f"Error adding message to {conv_id}: {e}")
            return False

    def update_conversation(self, conv_id: str, updates: dict) -> Optional[dict]:
        """Update conversation metadata."""
        meta_file = self.convs_dir / conv_id / "meta.json"
        if not meta_file.exists():
            return None

        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            
            meta.update(updates)
            meta["last_modified"] = int(__import__("time").time())

            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)

            return meta
        except Exception:
            return None

    def delete_conversation(self, conv_id: str) -> bool:
        """Delete a conversation."""
        import shutil
        conv_dir = self.convs_dir / conv_id
        if conv_dir.exists():
            try:
                shutil.rmtree(conv_dir)
                return True
            except Exception:
                return False
        return False

    def export_conversation(self, conv_id: str) -> Optional[dict]:
        """Export conversation as JSON for download."""
        conv = self.get_conversation(conv_id)
        if not conv:
            return None
        
        return {
            "metadata": conv["meta"],
            "messages": conv["messages"],
            "exported_at": datetime.now().isoformat(),
        }
