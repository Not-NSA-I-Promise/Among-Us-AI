"""Run every test. Usage:  python tests/run_all.py"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)


def main():
    tests = sorted(f for f in os.listdir(HERE)
                   if f.startswith("test_") and f.endswith(".py"))
    failed = []
    for t in tests:
        print("=" * 60)
        print("RUN", t)
        print("=" * 60)
        r = subprocess.run([sys.executable, os.path.join(HERE, t)],
                           cwd=ROOT, capture_output=True, text=True)
        out = (r.stdout or "") + (r.stderr or "")
        print(out.strip()[-2500:])
        print("-> exit", r.returncode)
        if r.returncode != 0:
            failed.append(t)
        print()
    print("=" * 60)
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    print(f"all {len(tests)} test files passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
