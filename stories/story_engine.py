"""
Story Engine - Core storytelling system for the trading bot.

Handles narrative generation, chapter management, and story state persistence.
"""

import json
import random
from pathlib import Path
from typing import Optional, Dict, List
from abc import ABC, abstractmethod


class BaseStory(ABC):
    """Abstract base class for all stories in the bot."""

    def __init__(self, story_id: str, title: str, description: str, target_audience: str):
        """
        Initialize a story.

        Args:
            story_id: Unique identifier for the story
            title: Story title
            description: Story description
            target_audience: Target audience demographic (e.g., "youth", "professionals")
        """
        self.story_id = story_id
        self.title = title
        self.description = description
        self.target_audience = target_audience
        self.chapters = {}
        self.current_chapter = 0
        self.total_chapters = random.randint(5, 10)
        self._setup_chapters()

    @abstractmethod
    def _setup_chapters(self) -> None:
        """Setup all story chapters. Must be implemented by subclass."""
        pass

    def get_chapter(self, chapter_num: int) -> Optional[Dict]:
        """
        Get a specific chapter.

        Args:
            chapter_num: Chapter number (0-indexed)

        Returns:
            Chapter dict with title and content, or None if not found
        """
        return self.chapters.get(chapter_num)

    def get_next_chapter(self) -> Optional[Dict]:
        """Get and advance to the next chapter."""
        if self.current_chapter < self.total_chapters:
            chapter = self.get_chapter(self.current_chapter)
            self.current_chapter += 1
            return chapter
        return None

    def get_current_chapter_number(self) -> int:
        """Get current chapter number (1-indexed for display)."""
        return self.current_chapter + 1

    def get_progress(self) -> str:
        """Get story progress as readable string."""
        return f"Chapter {self.get_current_chapter_number()}/{self.total_chapters}"

    def is_completed(self) -> bool:
        """Check if story is completed."""
        return self.current_chapter >= self.total_chapters

    def reset(self) -> None:
        """Reset story to beginning."""
        self.current_chapter = 0

    def get_story_intro(self) -> str:
        """Get story introduction message."""
        return f"""
🎭 **{self.title}**

{self.description}

📖 Total Chapters: {self.total_chapters}
👥 For: {self.target_audience}

Type /next_chapter to begin the journey...
"""


class StoryEngine:
    """Main story engine that manages all available stories."""

    def __init__(self, stories_dir: Optional[Path] = None):
        """
        Initialize story engine.

        Args:
            stories_dir: Path to stories directory (defaults to current module dir)
        """
        self.stories_dir = stories_dir or Path(__file__).parent
        self.stories: Dict[str, BaseStory] = {}
        self.active_story: Optional[BaseStory] = None
        self._register_stories()

    def _register_stories(self) -> None:
        """Register all available stories."""
        # Import here to avoid circular imports
        from stories.digital_freedom_quest import DigitalFreedomQuest

        # Register the Digital Freedom Quest story
        dq_story = DigitalFreedomQuest()
        self.stories[dq_story.story_id] = dq_story

    def get_available_stories(self) -> List[Dict]:
        """Get list of all available stories."""
        return [
            {
                "id": story.story_id,
                "title": story.title,
                "description": story.description,
                "audience": story.target_audience,
                "chapters": story.total_chapters
            }
            for story in self.stories.values()
        ]

    def start_story(self, story_id: str) -> bool:
        """
        Start a new story.

        Args:
            story_id: ID of story to start

        Returns:
            True if story started successfully
        """
        if story_id not in self.stories:
            return False

        self.active_story = self.stories[story_id]
        self.active_story.reset()
        return True

    def get_current_chapter(self) -> Optional[Dict]:
        """Get current chapter of active story."""
        if not self.active_story:
            return None
        return self.active_story.get_next_chapter()

    def get_story_status(self) -> Optional[str]:
        """Get current story status message."""
        if not self.active_story:
            return None

        progress = self.active_story.get_progress()
        status = f"📖 {self.active_story.title} - {progress}"

        if self.active_story.is_completed():
            status += "\n✅ Story completed! Well done, traveler."

        return status

    def save_progress(self, save_path: Path) -> None:
        """Save story progress to file."""
        if not self.active_story:
            return

        progress_data = {
            "story_id": self.active_story.story_id,
            "current_chapter": self.active_story.current_chapter,
            "total_chapters": self.active_story.total_chapters,
            "completed": self.active_story.is_completed()
        }

        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'w') as f:
            json.dump(progress_data, f, indent=2)

    def load_progress(self, save_path: Path) -> bool:
        """Load story progress from file."""
        if not save_path.exists():
            return False

        try:
            with open(save_path, 'r') as f:
                data = json.load(f)

            story_id = data.get("story_id")
            if not self.start_story(story_id):
                return False

            self.active_story.current_chapter = data.get("current_chapter", 0)
            return True
        except (json.JSONDecodeError, KeyError):
            return False
