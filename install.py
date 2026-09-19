#!/usr/bin/env python3
"""Procman install script (single-file Python program)

Installs the repository contents into a suitable directory in PATH.
If a newer version is already installed, it will be replaced.

Usage: /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/luke10x/procman/main/install.py)"
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile


def print_error(msg):
    sys.stderr.write(f"ERROR: {msg}\n")


def print_info(msg):
    sys.stdout.write(msg + "\n")


def fetch(url, dst_dir):
    try:
        import urllib.request
        urllib.request.urlretrieve(url, os.path.join(dst_dir, "proc"))
    except Exception as e:
        raise RuntimeError(f"Failed to download from {url}: {e}")


def run_proc_v(path):
    try:
        result = subprocess.run(
            [sys.executable, path, "-v"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to run ./proc -v: {e}")


def parse_semver(path):
    try:
        version = run_proc_v(path)
        match = re.match(r"(\d+)\.(\d+)\.(\d+)", version)
        if not match:
            raise ValueError(f"Unexpected version format: {version!r}")
        return tuple(int(x) for x in match.groups())
    except Exception as e:
        raise RuntimeError(f"Failed to parse version from {path}: {e}")


def get_install_target():
    primary = None

    # Prefer ~/.local/bin if it's in PATH and before ~/bin
    local_bin = os.path.expanduser("~/.local/bin")
    home_bin = os.path.expanduser("~/bin")

    parts = [p for p in os.environ.get("PATH", "").split(":") if p]
    idx_best = len(parts)
    best = -1
    for i, p in enumerate(parts):
        if local_bin in p:
            idx_best = i
            break
        if home_bin in p:
            best = i

    if idx_best != len(parts):
        if best == -1 or idx_best < best:
            primary = local_bin

    if primary is None and home_bin in parts:
        primary = home_bin

    # Else loop over all PATH dirs and pick the first writable
    if primary is None:
        for p in parts:
            if os.path.isdir(p) and os.access(p, os.W_OK):
                primary = p + "/procman"
                break

    return primary


def main():
    url = "https://raw.githubusercontent.com/luke10x/procman/main/proc"
    target = get_install_target()
    if target is None:
        print_error("No writable directory found in PATH to install Procman.")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp_dir:
        fetch(url, tmp_dir)

        try:
            downloaded_ver = parse_semver(os.path.join(tmp_dir, "proc"))
            installed_ver = None

            if os.path.exists(target + "/proc"):
                installed_ver = parse_semver(target + "/proc")

            print_info(f"Downloaded version: {downloaded_ver}")
            print_info(f"Installed version: {installed_ver or 'none'}")

            if installed_ver is not None and downloaded_ver <= installed_ver:
                print_info("Already up to date.")
            else:
                print_info("Newer version detected — reinstalling...")
                shutil.copy(os.path.join(tmp_dir, "proc"), target + "/proc")
                os.chmod(target + "/proc", 0o755)

        except Exception as e:
            print_error(f"Installation failed: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
