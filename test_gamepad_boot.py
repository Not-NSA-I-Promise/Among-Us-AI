"""Decisive test: does the game accept the virtual gamepad if the pad exists
BEFORE the game launches?

vgamepad registers a device with Windows when VX360Gamepad() is constructed.
If Among Us (Rewired) enumerates input devices only at startup, a pad created
afterwards is invisible to it.
"""
import subprocess
import sys
import time

import vgamepad as vg
import win32con
import win32gui

GAME = r"C:\Games\Among Us\Among Us.exe"
SEND = r"C:\Games\Among Us\sendData.txt"
GAMEDIR = r"C:\Games\Among Us"


def pos():
    with open(SEND) as f:
        p = f.readline().split()
    return (float(p[0]), float(p[1]))


def alive():
    for line in open(SEND):
        if line.strip() == "1":
            return True
    return False


print("1. killing the game")
subprocess.run(["taskkill", "/F", "/IM", "Among Us.exe"], capture_output=True)
time.sleep(3)

print("2. creating the virtual pad BEFORE the game starts")
pad = vg.VX360Gamepad()
pad.update()
print("   pad object:", pad)

print("3. launching the game")
subprocess.Popen([GAME], cwd=GAMEDIR)
print("   waiting for the game to load...")
time.sleep(50)

hwnd = win32gui.FindWindow(None, "Among Us")
if hwnd:
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
time.sleep(2)

import os
stale = not os.path.exists(SEND) or (time.time() - os.path.getmtime(SEND)) > 5
print("4. sendData fresh?", not stale)
if stale:
    print("   (no live match yet - start one, then press ENTER here)")
    input()

p0 = pos()
print(f"5. before : {p0}")
pad.left_joystick_float(x_value_float=1.0, y_value_float=0.0)
pad.update()
time.sleep(2.5)
p1 = pos()
pad.reset()
pad.update()
time.sleep(0.5)
d = ((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2) ** 0.5
print(f"   during : {p1}")
print(f"6. moved  : {d:.3f} tiles")
print("VERDICT:", "GAME ACCEPTS GAMEPAD (pad must pre-exist)" if d > 0.15
      else "STILL IGNORED - controller support likely disabled in the game")
