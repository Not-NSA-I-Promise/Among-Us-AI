"""Preflight check for the Among Us game window.

Template matching in task-solvers/ relies on the client area being 1920x1080.
The cv2 templates in task-solvers/cv2-templates were captured at that size and
task_utility.resize_images() scales them by (width/1920, height/1080). At any
other aspect ratio the game UI is laid out differently and matching fails.
"""
import sys

import win32gui

EXPECTED_W = 1920
EXPECTED_H = 1080

hwnd = win32gui.FindWindow(None, "Among Us")
if not hwnd:
    print("[FAIL] Among Us window not found - is the game running?")
    sys.exit(1)

l, t, r, b = win32gui.GetClientRect(hwnd)
w, h = r - l, b - t
x, y = win32gui.ClientToScreen(hwnd, (l, t))

print(f"[INFO] game client area: {w} x {h} (aspect {w / h:.4f}) at ({x},{y})")

if (w, h) == (EXPECTED_W, EXPECTED_H):
    print("[OK]   resolution is 1920x1080 - template matching will work")
    sys.exit(0)

print(f"[FAIL] resolution must be {EXPECTED_W}x{EXPECTED_H} (16:9), got {w}x{h}")
print(f"       scale factors would be {w / EXPECTED_W:.3f} x {h / EXPECTED_H:.3f}")
if abs(w / h - EXPECTED_W / EXPECTED_H) > 0.01:
    print("       aspect ratio is wrong (not 16:9) - task solving AND chat will break")
print("       Fix: close the game, then run  fix_resolution.ps1")
sys.exit(1)
