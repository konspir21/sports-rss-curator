"""Run groups independently and report any failure after attempting all groups."""
import subprocess
import sys
from pathlib import Path


def run_profiles(root=None):
    root = root or Path(__file__).parent
    failed = []
    for profile in ('sports', 'news', 'apple'):
        print(f'=== {profile} ===', flush=True)
        result = subprocess.run([sys.executable, str(root / 'curator.py'), '--profile', profile], cwd=root)
        if result.returncode:
            failed.append(profile)
    if failed:
        print('Failed profiles: ' + ', '.join(failed), file=sys.stderr)
    return bool(failed)


if __name__ == '__main__':
    sys.exit(run_profiles())
