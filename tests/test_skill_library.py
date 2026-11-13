import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from core.neo_skill_library import NEOSkillLibrary
from actions.skill_library_action import manage_skill_library, TOOL
from core.action_loader import discover_actions


class TestNEOSkillLibrary(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.routines_path = Path(self.tmp_dir.name) / "test_routines.json"
        self.lessons_path = Path(self.tmp_dir.name) / "test_lessons.json"
        self.lib = NEOSkillLibrary(
            routines_path=self.routines_path,
            lessons_path=self.lessons_path,
        )

    def tearDown(self):
        time.sleep(0.05)
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_save_and_find_routine(self):
        routine = self.lib.save_routine(
            name="open_youtube_music_chrome",
            goal="Open YouTube Music in Google Chrome and start playback",
            preconditions=["Google Chrome installed", "User is logged into Google"],
            steps=[
                "open_app(app_name='chrome')",
                "browser_control(action='navigate', url='https://music.youtube.com')",
                "wait for ready-signal: 'YouTube Music' in window title",
                "screen_click(description='Play button')",
            ],
            ready_signals=[
                "Window title contains 'YouTube Music'",
                "Play button visible",
            ],
        )

        self.assertEqual(routine["name"], "open_youtube_music_chrome")
        self.assertEqual(len(routine["steps"]), 4)
        self.assertEqual(routine["success_count"], 1)

        # Finding routine by keywords in goal
        matched = self.lib.find_matching_routine("open YouTube Music in chrome")
        self.assertIsNotNone(matched)
        self.assertEqual(matched["name"], "open_youtube_music_chrome")

        # Listing routines
        all_routines = self.lib.list_routines()
        self.assertEqual(len(all_routines), 1)

    def test_record_and_get_failure_lesson(self):
        lesson = self.lib.record_lesson(
            situation="Clicking the submit button on an animated modal dialog",
            what_went_wrong="Clicked before the button finished sliding in, resulting in a misclick",
            rule_to_prevent="Never click on an element while it is animating; wait for the modal to settle.",
        )

        self.assertEqual(lesson["situation"], "Clicking the submit button on an animated modal dialog")
        self.assertIn("Never click", lesson["rule_to_prevent"])

        lessons = self.lib.get_lessons()
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]["rule_to_prevent"], lesson["rule_to_prevent"])

    def test_prompt_synthesis_at_session_start(self):
        # Empty before adding lessons
        self.assertEqual(self.lib.synthesize_lessons_prompt(), "")

        # Add lesson
        self.lib.record_lesson(
            situation="Executing raw Enter in an unverified form field",
            what_went_wrong="Form was submitted prematurely with empty values",
            rule_to_prevent="Never press Enter/Submit until the typed content is verified.",
        )

        prompt_str = self.lib.synthesize_lessons_prompt()
        self.assertIn("FAILURE LESSONS & PREVENTATIVE RULES", prompt_str)
        self.assertIn("Never press Enter/Submit until the typed content is verified.", prompt_str)

        # Add routine
        self.lib.save_routine(
            name="git_status_check",
            goal="Check git repository status",
            preconditions=["In git repository root"],
            steps=["run_command(CommandLine='git status')"],
            ready_signals=["Exit code 0"],
        )
        routine_prompt = self.lib.synthesize_routines_prompt()
        self.assertIn("REUSABLE SKILL ROUTINE LIBRARY", routine_prompt)
        self.assertIn("git_status_check", routine_prompt)

    def test_tool_action_handler(self):
        from core.neo_skill_library import skill_library
        old_routines_path = skill_library.routines_path
        old_lessons_path = skill_library.lessons_path
        try:
            skill_library.routines_path = self.routines_path
            skill_library.lessons_path = self.lessons_path
            skill_library._routines = {}
            skill_library._lessons = []

            # Test save_routine
            res_save = manage_skill_library({
                "operation": "save_routine",
                "name": "test_routine",
                "goal": "Test goal for unit test",
                "preconditions": ["Precondition 1"],
                "steps": ["Step 1", "Step 2"],
                "ready_signals": ["Signal 1"],
            })
            self.assertIn("status=done action=save_routine", res_save)

            # Test find_routine
            res_find = manage_skill_library({
                "operation": "find_routine",
                "goal": "Test goal for unit test",
            })
            self.assertIn("status=done action=find_routine", res_find)
            self.assertIn("test_routine", res_find)

            # Test record_lesson
            res_lesson = manage_skill_library({
                "operation": "record_lesson",
                "situation": "Test situation",
                "what_went_wrong": "Test error",
                "rule_to_prevent": "Test rule to avoid regression",
            })
            self.assertIn("status=done action=record_lesson", res_lesson)

            # Test get_lessons
            res_get_lessons = manage_skill_library({
                "operation": "get_lessons",
            })
            self.assertIn("status=done count=", res_get_lessons)
            self.assertIn("Test rule to avoid regression", res_get_lessons)
        finally:
            skill_library.routines_path = old_routines_path
            skill_library.lessons_path = old_lessons_path
            skill_library._load()

    def test_action_loader_discovers_skill_library(self):
        reg = discover_actions(Path("actions"))
        decls = reg.get_tool_declarations()
        tool_names = [d["name"] for d in decls]
        self.assertIn("skill_library", tool_names)


if __name__ == "__main__":
    unittest.main()
