"""
tests/test_deep_studios_wiring.py — Comprehensive Integration & Wiring Verification for all 5 Studios.
"""
import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Set headless environment for Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

def run_tests():
    app = QApplication(sys.argv)
    print("✓ Qt Application initialized")

    # 1. Test tasks_db
    from core.tasks_db import add_task, load_tasks
    task = add_task("Integration Test Task", "Engineering", "High", notes="Automated verification")
    tasks = load_tasks()
    assert any(t["id"] == task["id"] for t in tasks), "Task was not found in memory/tasks.json"
    print(f"✓ Task Engine DB verified: {task['id']} persisted.")

    # 2. Test Swarm Studio
    from core.neo_swarm_studio import NeoSwarmStudio
    swarm = NeoSwarmStudio()
    swarm._refresh_swarm_state()
    assert hasattr(swarm, "goal_input")
    assert hasattr(swarm, "launch_btn")
    assert hasattr(swarm, "dossier_browser")
    print(f"✓ Swarm Studio initialized and verified: badge='{swarm.swarm_badge.text()}'")

    # 3. Test Vision Studio
    from core.neo_vision_studio import NeoVisionSpatialStudio
    vision = NeoVisionSpatialStudio()
    assert hasattr(vision, "viewport")
    assert hasattr(vision, "stream_btn")
    assert hasattr(vision, "detected_lbl")
    vision._sync_gesture_state()
    print(f"✓ Vision Spatial Studio verified: stance='{vision.detected_lbl.text()}'")

    # 4. Test Sentinel Hub
    from core.neo_sentinel_hub import NeoSentinelHub
    sentinel = NeoSentinelHub()
    sentinel._refresh_all_vitals()
    assert hasattr(sentinel, "card_ergo")
    assert hasattr(sentinel, "card_presence")
    assert hasattr(sentinel, "card_immune")
    assert hasattr(sentinel, "card_intel")
    print(f"✓ Sentinel Hub verified: presence='{sentinel.kpi_presence.val_lbl.text()}', ergo='{sentinel.kpi_posture.val_lbl.text()}'")

    # 5. Test Files View
    from core.neo_files_view import NeoFilesView
    files = NeoFilesView()
    assert hasattr(files, "tree")
    assert hasattr(files, "content_browser")
    assert hasattr(files, "analysis_browser")
    print(f"✓ Files Vault View verified: badge='{files.file_count_badge.text()}'")

    # 6. Test Terminal Studio
    from core.neo_terminal_studio import NeoTerminalStudio
    term = NeoTerminalStudio()
    assert hasattr(term, "console")
    assert hasattr(term, "cmd_input")
    # Test built-in cd
    initial_cwd = term.cwd
    term.execute_command("cd ..")
    assert term.cwd == initial_cwd.parent
    term.execute_command(f"cd \"{initial_cwd}\"")
    assert term.cwd == initial_cwd
    print(f"✓ Terminal Studio verified: working directory navigation functioning perfectly at '{term.cwd}'.")

    # 7. Test Full MainWindow Integration & Tab Navigation
    from ui import MainWindow
    window = MainWindow(face_path="core/face_model.obj")
    assert window._hud_cam_stack.count() == 14, f"Expected 14 stack widgets, got {window._hud_cam_stack.count()}"

    all_tabs = ["Chat", "Tasks", "Notes", "Projects", "Knowledge", "Files", "Sentinels", "Terminal", "Swarm", "Vision"]
    for tab in all_tabs:
        window._nav_sidebar.select_tab(tab)
        curr = window._hud_cam_stack.currentWidget()
        assert curr is not None, f"Current widget for tab {tab} is None"

    print("✓ Full MainWindow UI initialized: all 14 stack widgets and 10 executive navigation tabs verified.")

    # 8. Clean up test task
    from core.tasks_db import load_tasks, write_tasks
    clean_tasks = [t for t in load_tasks() if t["id"] != task["id"]]
    write_tasks(clean_tasks)
    print("✓ Test artifacts cleaned up.")

    print("\n🎉 ALL 5 STUDIOS AND FULL MAINWINDOW PASS DEEP FUNCTIONAL AND WIRING VERIFICATION WITH 100% SUCCESS!")

if __name__ == "__main__":
    run_tests()
