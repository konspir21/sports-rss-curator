"""Run isolated profile processes concurrently; retain partial-success handling."""
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def build_profile(root, profile):
    started = time.monotonic()
    print(f'Starting {profile}', flush=True)
    result = subprocess.run([sys.executable, str(root / 'curator.py'), '--profile', profile], cwd=root)
    print(f'Finished {profile} in {time.monotonic() - started:.1f}s (exit {result.returncode})', flush=True)
    return result.returncode


def run_profiles(root=None):
    root = root or Path(__file__).parent
    profiles = ('sports', 'news', 'apple')
    # Each subprocess owns separate config, feed and state files.
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda profile: build_profile(root, profile), profiles))
    failed = [profile for profile, code in zip(profiles, results) if code]
    if failed:
        print('Failed profiles: ' + ', '.join(failed), file=sys.stderr)
    return bool(failed)


if __name__ == '__main__':
    sys.exit(run_profiles())
