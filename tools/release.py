#!/usr/bin/env python
"""Cut Pulsar releases; see docs/developing.rst.

  release.py check            verify the current branch is ready to release
  release.py create [--next]  release commit, tag, and next .dev0 commit
  release.py branch           create release_X.Y from the release just cut on master
  release.py push             push branch(es) and tag to galaxyproject/pulsar
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

PROJECT_DIRECTORY = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HISTORY = "HISTORY.rst"
INIT = os.path.join("pulsar", "__init__.py")
GITHUB_REPO = "galaxyproject/pulsar"
HEADER_RULE = "-" * 21
VERSION_LINE = re.compile(r"^__version__ = '([^']+)'$", re.MULTILINE)
DEV_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)\.dev\d+$")
RELEASE_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
PR_MERGE = re.compile(r"^Merge pull request #(\d+) from (\S+)")
REFERENCE = re.compile(r"`([^`<>]+)`_(?!\w)")
TARGET = re.compile(r"^\.\. _([^:]+):", re.MULTILINE)


class ReleaseError(Exception):
    pass


def git(*args, check=True):
    result = subprocess.run(["git", *args], cwd=PROJECT_DIRECTORY, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def read(path):
    with open(os.path.join(PROJECT_DIRECTORY, path), encoding="utf-8") as f:
        return f.read()


def write(path, contents):
    with open(os.path.join(PROJECT_DIRECTORY, path), "w", encoding="utf-8") as f:
        f.write(contents)


def current_version():
    match = VERSION_LINE.search(read(INIT))
    if not match:
        raise ReleaseError(f"no __version__ in {INIT}")
    return match.group(1)


def set_version(init, version):
    return VERSION_LINE.sub(f"__version__ = '{version}'", init, count=1)


def release_version(dev_version):
    match = DEV_VERSION.match(dev_version)
    if not match:
        raise ReleaseError(f"version {dev_version} is not a .devN version")
    return ".".join(match.groups())


def version_tuple(version):
    match = RELEASE_VERSION.match(version)
    if not match:
        raise ReleaseError(f"{version} is not an X.Y.Z version")
    return tuple(int(part) for part in match.groups())


def next_patch(version):
    major, minor, patch = version_tuple(version)
    return f"{major}.{minor}.{patch + 1}"


def series(version):
    major, minor, _ = version_tuple(version)
    return f"{major}.{minor}"


def top_header(history):
    lines = history.split(".. to_doc\n", 1)[1].splitlines()
    for previous, line in zip(lines, lines[1:]):
        if previous == HEADER_RULE and line.strip():
            return line.strip()
    raise ReleaseError(f"no version header under .. to_doc in {HISTORY}")


def mark_released(history, dev_version, version, date):
    header = f"\n{dev_version}\n"
    if top_header(history) != dev_version:
        raise ReleaseError(f"top {HISTORY} section is {top_header(history)}, expected {dev_version}")
    return history.replace(header, f"\n{version} ({date})\n", 1)


def start_version(history, version):
    section = f"\n{HEADER_RULE}\n{version}.dev0\n{HEADER_RULE}\n\n\n"
    return history.replace(".. to_doc\n", ".. to_doc\n" + section, 1)


def references(history):
    return {" ".join(ref.split()) for ref in REFERENCE.findall(history)}


def missing_history_prs(history, merge_subjects):
    referenced = references(history)
    missing = []
    for subject in merge_subjects:
        match = PR_MERGE.match(subject)
        if not match or "dependabot" in match.group(2):
            continue
        number = match.group(1)
        if f"Pull Request {number}" not in referenced:
            missing.append(number)
    return missing


def missing_targets(history):
    targets = set(TARGET.findall(history))
    return sorted(references(history) - targets)


def upstream_remote():
    for line in git("remote", "-v").splitlines():
        name, url, kind = line.split()
        if kind == "(push)" and re.search(rf"[:/]{GITHUB_REPO}(\.git)?/?$", url):
            return name
    raise ReleaseError(f"no git remote points at {GITHUB_REPO}")


def current_branch():
    return git("rev-parse", "--abbrev-ref", "HEAD")


def latest_tag():
    return git("describe", "--tags", "--abbrev=0", "HEAD")


def merge_subjects(previous):
    """Subjects of merges on this branch since ``previous``, and on release branches merged into it.

    First-parent history skips PR merges made on forks, but would also skip PRs
    that reach master through a release branch merge, so follow those.
    """
    subjects, seen, tips = [], set(), ["HEAD"]
    while tips:
        log = git("log", "--first-parent", "--merges", "--format=%H %P%x00%s", f"{previous}..{tips.pop()}")
        for line in log.splitlines():
            shas, subject = line.split("\0", 1)
            sha, *parents = shas.split()
            if sha in seen:
                continue
            seen.add(sha)
            subjects.append(subject)
            if "release_" in subject:
                tips.extend(parents[1:])
    return subjects


def ci_problems(sha):
    """Return (errors, warnings) for GitHub Actions runs on ``sha``."""
    if not shutil.which("gh"):
        return [], ["gh not installed; check CI by hand"]
    result = subprocess.run(
        ["gh", "run", "list", "--repo", GITHUB_REPO, "--commit", sha, "--json", "name,status,conclusion"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return [f"could not query CI: {result.stderr.strip()}"], []
    runs = json.loads(result.stdout)
    if not runs:
        return [f"no CI runs found for {sha[:10]}"], []
    errors = []
    for run in runs:
        if run["status"] != "completed":
            errors.append(f"CI run {run['name']} is {run['status']}")
        elif run["conclusion"] not in ("success", "skipped", "neutral"):
            errors.append(f"CI run {run['name']} concluded {run['conclusion']}")
    return errors, []


def check(allow_missing_history=False, skip_ci=False):
    errors, warnings = [], []
    dev_version = current_version()
    try:
        version = release_version(dev_version)
    except ReleaseError as e:
        raise ReleaseError(f"{e}; is a release already in progress?")
    branch = current_branch()
    if branch == "master":
        pass
    elif branch.startswith("release_"):
        if branch != f"release_{series(version)}":
            errors.append(f"version {dev_version} does not belong on {branch}")
    else:
        errors.append(f"releases are cut from master or release_X.Y, not {branch}")
    if git("status", "--porcelain"):
        errors.append("working tree is not clean")
    if git("tag", "--list", version):
        errors.append(f"tag {version} already exists locally")

    remote = upstream_remote()
    if git("ls-remote", "--tags", remote, f"refs/tags/{version}"):
        errors.append(f"tag {version} already exists on {remote}")
    git("fetch", "--quiet", remote, branch, check=False)
    remote_sha = git("rev-parse", "--verify", "--quiet", "FETCH_HEAD", check=False)
    head = git("rev-parse", "HEAD")
    if remote_sha != head:
        errors.append(f"{branch} differs from {remote}/{branch}; pull or push first")

    history = read(HISTORY)
    header = top_header(history)
    if header != dev_version:
        errors.append(f"top {HISTORY} section is {header}, expected {dev_version}")
    try:
        previous = latest_tag()
    except ReleaseError:
        previous = None
        warnings.append("no previous tag; skipping HISTORY coverage check")
    if previous:
        missing = missing_history_prs(history, merge_subjects(previous))
        if missing:
            message = f"{HISTORY} is missing PRs merged since {previous}: {', '.join(missing)}"
            message += " (make add-history ITEM=prN adds one)"
            (warnings if allow_missing_history else errors).append(message)
    for target in missing_targets(history):
        errors.append(f"{HISTORY} references `{target}`_ with no target")

    ci_errors, ci_warnings = ci_problems(head)
    (warnings if skip_ci else errors).extend(ci_errors)
    warnings.extend(ci_warnings)

    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    if errors:
        raise ReleaseError(f"not ready to release {version}")
    print(f"ready to release {version} from {branch}")
    return version


def commit_start_version(version):
    write(HISTORY, start_version(read(HISTORY), version))
    write(INIT, set_version(read(INIT), f"{version}.dev0"))
    git("commit", "--quiet", "-m", f"Start work on {version}", HISTORY, INIT)


def validate_next_version(version, next_version, branch):
    if version_tuple(next_version) <= version_tuple(version):
        raise ReleaseError(f"next version {next_version} must be after {version}")
    if branch.startswith("release_") and series(next_version) != series(version):
        raise ReleaseError(f"next version {next_version} does not belong on {branch}")


def create(next_version=None, allow_missing_history=False, skip_ci=False):
    dev_version = current_version()
    next_version = next_version or next_patch(release_version(dev_version))
    validate_next_version(release_version(dev_version), next_version, current_branch())
    version = check(allow_missing_history, skip_ci)
    today = datetime.date.today().isoformat()
    write(HISTORY, mark_released(read(HISTORY), dev_version, version, today))
    write(INIT, set_version(read(INIT), version))
    git("commit", "--quiet", "-m", f"Create pulsar release {version}", HISTORY, INIT)
    git("tag", version)
    commit_start_version(next_version)
    print(git("log", "--oneline", "--decorate", "-2"))
    if current_branch() == "master" and series(next_version) != series(version):
        print(f"next: make release-branch (creates release_{series(version)}), then make push-release")
    else:
        print("next: make push-release")


def just_released():
    """Return the tag that HEAD~1 is, if HEAD is the 'Start work on' commit after a release."""
    tag = latest_tag()
    if git("rev-parse", f"{tag}^{{commit}}") != git("rev-parse", "HEAD~1"):
        raise ReleaseError(f"HEAD~1 is not tag {tag}; run make release first")
    return tag


def branch():
    if current_branch() != "master":
        raise ReleaseError("release branches are cut from master")
    tag = just_released()
    name = f"release_{series(tag)}"
    if series(release_version(current_version())) == series(tag):
        raise ReleaseError(f"master is still on the {series(tag)} series; rerun make release with NEXT=X.Y.0")
    if git("branch", "--list", name) or git("ls-remote", "--heads", upstream_remote(), name):
        raise ReleaseError(f"{name} already exists")
    git("switch", "--quiet", "-c", name, tag)
    try:
        commit_start_version(next_patch(tag))
        print(git("log", "--oneline", "--decorate", "-1"))
    finally:
        git("switch", "--quiet", "master")
    print("next: make push-release")


def push():
    tag = just_released()
    remote = upstream_remote()
    branches = [current_branch()]
    # After make release-branch, the new release branch goes out with master.
    release_branch = f"release_{series(tag)}"
    if (
        branches[0] != release_branch
        and git("branch", "--list", release_branch)
        and not git("ls-remote", "--heads", remote, release_branch)
    ):
        branches.append(release_branch)
    command = ["push", "--atomic", remote, *branches, tag]
    print(f"git {' '.join(command)}")
    print(f"Pushing tag {tag} publishes pulsar-app and pulsar-galaxy-lib to PyPI.")
    if input("Continue? [y/N] ").strip().lower() != "y":
        raise ReleaseError("not pushed")
    git(*command)
    print(f"""
Watch: https://github.com/{GITHUB_REPO}/actions/workflows/deploy.yaml
Check: https://pypi.org/project/pulsar-app/{tag}/
       https://pypi.org/project/pulsar-galaxy-lib/{tag}/
Then:  gh release create {tag} --repo {GITHUB_REPO} --verify-tag --generate-notes""")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "create"):
        command = commands.add_parser(name)
        command.add_argument("--allow-missing-history", action="store_true")
        command.add_argument("--skip-ci", action="store_true", help="warn instead of failing on CI problems")
    commands.choices["create"].add_argument("--next", help="next version (default: next patch release)")
    commands.add_parser("branch")
    commands.add_parser("push")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            check(args.allow_missing_history, args.skip_ci)
        elif args.command == "create":
            create(args.next, args.allow_missing_history, args.skip_ci)
        elif args.command == "branch":
            branch()
        else:
            push()
    except ReleaseError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
