"""Initialize/sync the pinned experimental AOSP tree on the physical ext4 disk."""

import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


UUID = "a00da05f-1eb2-44b6-99f0-9109391f67dc"
VOLUME = Path("/mnt/wsl/PHYSICALDRIVE5p3")
PROJECT = VOLUME / "home/red_panda/RedPandaAndroid"
SOURCE = PROJECT / "pico4-pro/source/aosp-10"
REPO_TOOL = PROJECT / "source/.repo/repo"
REPO_VERSION = "v2.68.1"
REPO_COMMIT = "e1e215a14ea5373419acb8753b6865de19d1f122"
TAG = "android-10.0.0_r47"
REPORT = Path(__file__).resolve().parents[1] / "reports/aosp-preparation"
LOGS = PROJECT / "pico4-pro/logs/aosp"


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync", action="store_true", help="Sync sources after initialization (8 CPU maximum)")
    args = parser.parse_args()
    if sys.platform != "linux":
        raise RuntimeError("Run inside WSL")
    mounts = json.loads(subprocess.check_output([
        "findmnt", "--json", "--output", "TARGET,FSTYPE,UUID", "--target", str(VOLUME),
    ], text=True))["filesystems"]
    if len(mounts) != 1 or mounts[0]["fstype"] != "ext4" or mounts[0]["uuid"] != UUID:
        raise RuntimeError("Expected ext4 volume is not mounted")
    if Path(mounts[0]["target"]).resolve() != VOLUME.resolve() or not PROJECT.is_dir():
        raise RuntimeError("Unexpected project/mount location")
    if not SOURCE.resolve().is_relative_to((PROJECT / "pico4-pro").resolve()):
        raise RuntimeError("Source directory escapes the PICO project")
    if git(REPO_TOOL, "rev-parse", "HEAD") != REPO_COMMIT or git(REPO_TOOL, "status", "--porcelain"):
        raise RuntimeError("Existing repo tool revision/local changes differ from the inspected version")
    if shutil.disk_usage(VOLUME).free < 80 * 1024 ** 3:
        raise RuntimeError("Less than 80 GiB free for source preparation")
    if SOURCE.exists() and any(SOURCE.iterdir()) and not (SOURCE / ".repo").is_dir():
        raise RuntimeError("Preserve an existing unrelated source directory")
    SOURCE.mkdir(parents=True, exist_ok=True)
    REPORT.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    state = {
        "source_root": str(SOURCE), "manifest_url": "https://android.googlesource.com/platform/manifest",
        "aosp_tag": TAG, "repo_version": REPO_VERSION, "repo_tool_commit": REPO_COMMIT,
        "volume_uuid": UUID, "max_cpus": 8, "pid": os.getpid(), "started_at": now(),
        "experimental_base_not_proven_original_pico_revision": True,
        "source_sync_completed": False, "custom_build_started": False,
    }

    def save(stage):
        state.update(stage=stage, updated_at=now())
        (REPORT / "status.json").write_text(json.dumps(state, indent=2) + "\n")
        print(stage, flush=True)

    environment = os.environ.copy()
    environment.update({"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_COUNT": "2",
                        "GIT_CONFIG_KEY_0": "user.name", "GIT_CONFIG_VALUE_0": "Android Builder",
                        "GIT_CONFIG_KEY_1": "user.email", "GIT_CONFIG_VALUE_1": "build@localhost"})
    command = [sys.executable, str(REPO_TOOL / "repo")]
    if not (SOURCE / ".repo/manifest.xml").exists():
        save("initializing")
        with (LOGS / "init.log").open("a") as log:
            result = subprocess.run(["taskset", "-c", "0-7", *command, "init", "-u", state["manifest_url"],
                "-b", "refs/tags/" + TAG, "--depth=1", "--no-clone-bundle",
                "--repo-url", str(REPO_TOOL), "--repo-rev", REPO_VERSION],
                cwd=SOURCE, env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        if result.returncode:
            state["exit_code"] = result.returncode
            save("initialization-failed")
            raise SystemExit(result.returncode)
    manifest = SOURCE / ".repo/manifests"
    state["manifest_commit"] = git(manifest, "rev-parse", "HEAD")
    state["manifest_tag_commit"] = git(manifest, "rev-parse", "refs/tags/" + TAG + "^{commit}")
    if state["manifest_commit"] != state["manifest_tag_commit"] or git(manifest, "status", "--porcelain"):
        raise RuntimeError("Existing manifest is not the pinned clean AOSP tag")
    (REPORT / "default.xml").write_bytes((SOURCE / ".repo/manifest.xml").read_bytes())
    save("initialized")
    if args.sync:
        save("syncing")
        with (LOGS / "sync.log").open("a") as log:
            result = subprocess.run(["taskset", "-c", "0-7", *command, "sync", "-c", "--no-tags",
                "--no-clone-bundle", "--fail-fast", "-j8"],
                cwd=SOURCE, env=environment, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        state["exit_code"] = result.returncode
        if result.returncode:
            save("sync-failed")
            raise SystemExit(result.returncode)
        state["source_sync_completed"] = True
        save("synced")


if __name__ == "__main__":
    main()
