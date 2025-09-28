#!/usr/bin/env python3

"""
Auto Git committer (README-friendly)

Adds a line to a target file (e.g., README.md) every N seconds, commits, and pushes.
You can customize the text via --line-template and choose to append or prepend.

Examples:
  python3 auto_committer_readme.py --repo /path/to/repo --branch main \
    --file README.md --interval 1 --line-template "- heartbeat {ts}"

  # Prepend to the top of README instead of appending:
  python3 auto_committer_readme.py --repo /path/to/repo --branch main \
    --file README.md --interval 5 --line-template "* updated at {ts}" --prepend

Notes:
  - Requires: git CLI; repo cloned; push auth configured.
  - Heavy push frequency can trigger rate limits on hosting providers.
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

def sh(cmd, cwd, env=None):
    r = subprocess.run(cmd, cwd=cwd, env=env, check=True, capture_output=True, text=True)
    return r.stdout.strip()

def ensure_branch(repo: Path, branch: str):
    try:
        sh(["git", "rev-parse", "--verify", branch], cwd=repo)
        sh(["git", "checkout", branch], cwd=repo)
    except subprocess.CalledProcessError:
        sh(["git", "checkout", "-b", branch], cwd=repo)

def write_line(file_path: Path, line: str, prepend: bool):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if prepend:
        # Prepend: read existing, write new line + existing
        existing = ""
        if file_path.exists():
            existing = file_path.read_text(encoding="utf-8", errors="ignore")
        with file_path.open("w", encoding="utf-8") as f:
            f.write(line + ("\n" if not line.endswith("\n") else ""))
            f.write(existing)
    else:
        with file_path.open("a", encoding="utf-8") as f:
            f.write(line + ("\n" if not line.endswith("\n") else ""))

def main():
    ap = argparse.ArgumentParser(description="Loop commits that update a target file (e.g., README.md).")
    ap.add_argument("--repo", required=True, help="Path to local git repository")
    ap.add_argument("--branch", required=True, help="Branch to commit to / push")
    ap.add_argument("--remote", default="origin", help="Remote name (default: origin)")
    ap.add_argument("--file", default="README.md", help="File to modify each commit (default: README.md)")
    ap.add_argument("--interval", type=float, default=1.0, help="Seconds between commits (default: 1.0)")
    ap.add_argument("--message", default="[bot] heartbeat", help="Commit message prefix")
    ap.add_argument("--author", default=None, help='Override commit author, e.g. "Auto Bot <bot@example.com>"')
    ap.add_argument("--line-template", default="- heartbeat {ts}", help="Text to insert; supports {ts} placeholder")
    ap.add_argument("--prepend", action="store_true", help="Insert at the top of the file (default: append to bottom)")
    ap.add_argument("--no-push", action="store_true", help="Do not push to remote (local commits only)")
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if not (repo / ".git").exists():
        print(f"ERROR: {repo} does not look like a git repository (.git missing)", file=sys.stderr)
        sys.exit(2)

    # Warn if working tree has changes
    try:
        status = sh(["git", "status", "--porcelain"], cwd=repo)
        if status:
            print("NOTE: Working tree has changes; they may be included in commits.", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(e.stderr, file=sys.stderr)
        sys.exit(3)

    ensure_branch(repo, args.branch)
    target_path = repo / args.file
    print(f"Starting: repo={repo}, branch={args.branch}, file={args.file}, every {args.interval}s")

    try:
        while True:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            line = args.line-template if hasattr(args, "line-template") else args.line_template  # guard for hyphen
            # Python can't use args.line-template; the parser stored it as line_template
            line = args.line_template.format(ts=ts)
            write_line(target_path, line, args.prepend)

            rel = str(target_path.relative_to(repo))
            sh(["git", "add", rel], cwd=repo)

            commit_cmd = ["git", "commit", "-m", f"{args.message} {ts}"]
            if args.author:
                commit_cmd += ["--author", args.author]

            try:
                sh(commit_cmd, cwd=repo)
            except subprocess.CalledProcessError as e:
                if "nothing to commit" in (e.stdout + e.stderr).lower():
                    pass
                else:
                    print("Commit failed:\n", e.stdout, e.stderr, file=sys.stderr)
                    time.sleep(args.interval)
                    continue

            if not args.no_push:
                try:
                    sh(["git", "push", args.remote, args.branch], cwd=repo)
                except subprocess.CalledProcessError as e:
                    print("Push failed (will retry on next loop):\n", e.stdout, e.stderr, file=sys.stderr)

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped by user.")

if __name__ == "__main__":
    main()
