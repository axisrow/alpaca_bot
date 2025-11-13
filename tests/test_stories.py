"""Tests for the storytelling system."""

import pytest
from stories.story_engine import StoryEngine, BaseStory
from stories.digital_freedom_quest import DigitalFreedomQuest


class TestBaseStory:
    """Test BaseStory class functionality."""

    def test_story_initialization(self):
        """Test story initialization."""
        story = DigitalFreedomQuest()

        assert story.story_id == "digital_freedom_quest"
        assert story.title == "🚀 Digital Freedom Quest"
        assert story.target_audience == "Youth (Gen Z & Young Millennials, 18-35)"
        assert 5 <= story.total_chapters <= 10

    def test_chapter_count_random(self):
        """Test that chapter count is random between 5-10."""
        chapters_count = set()

        for _ in range(20):
            story = DigitalFreedomQuest()
            chapters_count.add(story.total_chapters)

        # Should have multiple different chapter counts over 20 iterations
        assert len(chapters_count) >= 2
        assert all(5 <= count <= 10 for count in chapters_count)

    def test_get_chapter(self):
        """Test retrieving a specific chapter."""
        story = DigitalFreedomQuest()

        chapter = story.get_chapter(0)
        assert chapter is not None
        assert "title" in chapter
        assert "emoji" in chapter
        assert "content" in chapter
        assert "number" in chapter

    def test_get_next_chapter(self):
        """Test advancing through chapters."""
        story = DigitalFreedomQuest()

        initial_chapter_num = story.current_chapter

        chapter = story.get_next_chapter()
        assert chapter is not None
        assert story.current_chapter == initial_chapter_num + 1

    def test_get_progress(self):
        """Test progress message format."""
        story = DigitalFreedomQuest()
        progress = story.get_progress()

        assert "Chapter" in progress
        assert "/" in progress
        assert str(story.total_chapters) in progress

    def test_is_completed(self):
        """Test story completion detection."""
        story = DigitalFreedomQuest()

        assert not story.is_completed()

        # Advance through all chapters
        while story.current_chapter < story.total_chapters:
            story.get_next_chapter()

        assert story.is_completed()

    def test_reset(self):
        """Test story reset functionality."""
        story = DigitalFreedomQuest()

        # Advance some chapters
        story.get_next_chapter()
        story.get_next_chapter()

        assert story.current_chapter == 2

        # Reset
        story.reset()
        assert story.current_chapter == 0

    def test_get_story_intro(self):
        """Test story introduction format."""
        story = DigitalFreedomQuest()
        intro = story.get_story_intro()

        assert story.title in intro
        assert story.description in intro
        assert "Chapters" in intro or "chapters" in intro


class TestStoryEngine:
    """Test StoryEngine class functionality."""

    def test_engine_initialization(self):
        """Test story engine initialization."""
        engine = StoryEngine()

        assert engine.stories is not None
        assert len(engine.stories) > 0
        assert engine.active_story is None

    def test_get_available_stories(self):
        """Test retrieving available stories."""
        engine = StoryEngine()
        stories = engine.get_available_stories()

        assert len(stories) > 0

        story = stories[0]
        assert "id" in story
        assert "title" in story
        assert "description" in story
        assert "audience" in story
        assert "chapters" in story

    def test_start_story_valid(self):
        """Test starting a valid story."""
        engine = StoryEngine()

        result = engine.start_story("digital_freedom_quest")
        assert result is True
        assert engine.active_story is not None
        assert engine.active_story.story_id == "digital_freedom_quest"

    def test_start_story_invalid(self):
        """Test starting an invalid story."""
        engine = StoryEngine()

        result = engine.start_story("nonexistent_story")
        assert result is False
        assert engine.active_story is None

    def test_get_current_chapter(self):
        """Test retrieving current chapter."""
        engine = StoryEngine()

        # Without active story
        chapter = engine.get_current_chapter()
        assert chapter is None

        # With active story
        engine.start_story("digital_freedom_quest")
        chapter = engine.get_current_chapter()
        assert chapter is not None
        assert "title" in chapter
        assert "content" in chapter

    def test_get_story_status(self):
        """Test story status message."""
        engine = StoryEngine()

        # Without active story
        status = engine.get_story_status()
        assert status is None

        # With active story
        engine.start_story("digital_freedom_quest")
        status = engine.get_story_status()
        assert status is not None
        assert "digital_freedom_quest" in engine.active_story.title.lower()

    def test_story_completion_flow(self):
        """Test complete story reading flow."""
        engine = StoryEngine()

        # Start story
        assert engine.start_story("digital_freedom_quest")
        story = engine.active_story
        total_chapters = story.total_chapters

        # Read all chapters
        for _ in range(total_chapters):
            chapter = engine.get_current_chapter()
            assert chapter is not None

        # Next chapter should be None (story completed)
        chapter = engine.get_current_chapter()
        assert chapter is None
        assert story.is_completed()

    def test_story_reset_via_engine(self):
        """Test resetting story via engine."""
        engine = StoryEngine()

        engine.start_story("digital_freedom_quest")
        first_chapter = engine.get_current_chapter()

        # Start new story (resets old one)
        engine.start_story("digital_freedom_quest")
        new_first_chapter = engine.get_current_chapter()

        # First chapter should be same (we're starting fresh)
        assert first_chapter["number"] == new_first_chapter["number"]


class TestDigitalFreedomQuest:
    """Test Digital Freedom Quest specific functionality."""

    def test_dq_is_registered(self):
        """Test that Digital Freedom Quest is registered."""
        engine = StoryEngine()
        stories = engine.get_available_stories()

        story_ids = [s["id"] for s in stories]
        assert "digital_freedom_quest" in story_ids

    def test_dq_target_audience(self):
        """Test that DQ is aimed at youth."""
        story = DigitalFreedomQuest()

        assert "Youth" in story.target_audience or "Gen Z" in story.target_audience

    def test_dq_all_chapters_have_content(self):
        """Test that all DQ chapters have proper content."""
        story = DigitalFreedomQuest()

        for i in range(story.total_chapters):
            chapter = story.get_chapter(i)
            assert chapter is not None
            assert chapter["title"] is not None
            assert len(chapter["title"]) > 0
            assert chapter["emoji"] is not None
            assert chapter["content"] is not None
            assert len(chapter["content"]) > 100  # Meaningful content

    def test_dq_unique_chapters(self):
        """Test that DQ doesn't have duplicate chapters."""
        story1 = DigitalFreedomQuest()
        story2 = DigitalFreedomQuest()

        # Different instances should have same chapters (unique selection)
        titles1 = [ch["title"] for ch in story1.chapters.values()]
        titles2 = [ch["title"] for ch in story2.chapters.values()]

        # At least verify no duplicates within single story
        assert len(titles1) == len(set(titles1))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
