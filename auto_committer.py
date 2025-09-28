#!/usr/bin/env python3

"""
Auto Git committer: writes/updates a heartbeat file and commits+pushes on a loop.
Use at your own risk (CI/CD and Git hosting may rate-limit or block very frequent pushes).

Example:
  python3 auto_committer.py --repo /path/to/repo --branch my-feature --interval 1

Requirements:
  - git CLI installed and in PATH
  - repo is already cloned locally
  - you are authenticated for push (SSH key or credential manager)
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

def sh(cmd, cwd, env=None):
    """Run a shell command and return stdout. Raises on non-zero status."""
    r = subprocess.run(cmd, cwd=cwd, env=env, check=True, capture_output=True, text=True)
    return r.stdout.strip()

def ensure_branch(repo: Path, branch: str):
    # Try to checkout the branch if it exists, otherwise create it from current HEAD
    try:
        sh(["git", "rev-parse", "--verify", branch], cwd=repo)
        sh(["git", "checkout", branch], cwd=repo)
    except subprocess.CalledProcessError:
        sh(["git", "checkout", "-b", branch], cwd=repo)

def write_heartbeat(file_path: Path):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    payload = f"heartbeat: {now}\n"
    # Append to keep history in file
    with file_path.open("a", encoding="utf-8") as f:
        f.write(payload)
    return now

def main():
    ap = argparse.ArgumentParser(description="Loop commits to a branch on a fixed interval.")
    ap.add_argument("--repo", required=True, help="Path to local git repository")
    ap.add_argument("--branch", required=True, help="Branch to commit to / push")
    ap.add_argument("--remote", default="origin", help="Remote name (default: origin)")
    ap.add_argument("--file", default=".autocommit/heartbeat.txt", help="File to touch each commit")
    ap.add_argument("--interval", type=float, default=1.0, help="Seconds between commits (default: 1.0)")
    ap.add_argument("--message", default="[bot] heartbeat", help="Commit message prefix")
    ap.add_argument("--author", default=None, help='Override commit author, e.g. "Auto Bot <bot@example.com>"')
    ap.add_argument("--no-push", action="store_true", help="Do not push to remote (local commits only)")
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if not (repo / ".git").exists():
        print(f"ERROR: {repo} does not look like a git repository (.git missing)", file=sys.stderr)
        sys.exit(2)

    # Ensure clean working tree state is not strictly required, but warn
    try:
        status = sh(["git", "status", "--porcelain"], cwd=repo)
        if status:
            print("NOTE: Working tree has changes; they may be included in commits.", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(e.stderr, file=sys.stderr)
        sys.exit(3)

    # Checkout / create the branch
    ensure_branch(repo, args.branch)

    print(f"Starting loop: repo={repo}, branch={args.branch}, remote={args.remote}, every {args.interval}s")
    heartbeat_path = (repo / args.file)

    try:
        while True:
            ts = write_heartbeat(heartbeat_path)
            # Stage and commit
            sh(["git", "add", str(heartbeat_path.relative_to(repo))], cwd=repo)
            commit_cmd = ["git", "commit", "-m", f"{args.message} {ts}"]
            if args.author:
                commit_cmd += ["--author", args.author]
            try:
                sh(commit_cmd, cwd=repo)
            except subprocess.CalledProcessError as e:
                # If there's nothing to commit (shouldn't happen since we append), skip gracefully
                if "nothing to commit" in (e.stdout + e.stderr).lower():
                    pass
                else:
                    print("Commit failed:\n", e.stdout, e.stderr, file=sys.stderr)
                    time.sleep(args.interval)
                    continue

            if not args.no-push:
                try:
                    sh(["git", "push", args.remote, args.branch], cwd=repo)
                except subprocess.CalledProcessError as e:
                    print("Push failed (will retry on next loop):\n", e.stdout, e.stderr, file=sys.stderr)

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped by user.")

if __name__ == "__main__":
    main()
