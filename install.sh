#!/usr/bin/env bash
#
# Procman install script
# Installs the repository contents into a suitable directory in PATH.
#
# Usage: /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/luke10x/procman/main/install.sh)"
#
# Logic:
#   1. Check if ~/.local/bin is in PATH and appears before ~/bin.
#      If yes, use ~/.local/bin as the install target.
#   2. Else check if ~/bin is in PATH.
#      If yes, use ~/bin as the install target.
#   3. Else loop over all directories in PATH in order and pick the first one
#      where we can create a new directory (and write to it).
#   4. If no suitable target is found, fail with an error message.
#
# The script copies the repository contents into the chosen target directory.
# It does not overwrite an already-installed Procman (detects by presence of
# key files).

set -euo pipefail

trap 'print_error "Installation failed at line $LINENO"' ERR

print_error() {
    echo >&2 "ERROR: $*"
}

print_info() {
    echo "$*"
}

# Check whether a directory is in PATH and its sort order relative to another.
path_index() {
    local dir="$1"
    local -i idx=-2   # -2 means not found
    local -i best=-1  # track index of the "best" candidate seen so far
    local -a parts
    IFS=':' read -ra parts <<< "$PATH"
    for i in "${!parts[@]}"; do
        if [[ "${parts[$i]}" == *"$dir"* ]]; then
            idx=$i
            # If this is the first time we see this dir, or it's before the best,
            # update best. (We only care about relative order between ~/.local/bin and ~/bin.)
            if ((best < 0 || i < best)); then
                best=$i
            fi
            break
        fi
    done
    echo "$idx:$best"
}

# Try to install into the given directory.
try_install() {
    local target="$1"
    print_info "Trying to install into: $target"
    if [[ -d "$target" ]]; then
        # Check if Procman is already installed here (any of the key files)
        if ls "$target"/proc "$target"/README.md "$target"/LICENSE 2>/dev/null | grep -q .; then
            print_info "Already installed at $target — nothing to do."
            return 0
        fi
    fi
    # Ensure we can create the directory
    if ! mkdir -p "$target"; then
        print_error "Cannot create directory: $target"
        return 1
    fi
    # Copy repository contents into target (excluding this script itself to avoid recursion)
    cp --no-dereference ./* ./.?* "$target/" 2>/dev/null || true
    chmod +x "$target"/proc
    print_info "Installed to: $target"
    return 0
}

# Determine the primary install target.
primary_target=""
if [[ -n "$(path_index ~/.local/bin)" ]]; then
    # ~/.local/bin is in PATH; check if it's before ~/bin
    local idx_best
    idx_best="$(path_index ~/.local/bin)"
    local idx_local_bin
    idx_local_bin="${idx_best%%:*}"
    local idx_home_bin
    idx_home_bin="${idx_best##*:}"
    if ((idx_local_bin < idx_home_bin)); then
        primary_target="$HOME/.local/bin/procman"
    else
        primary_target="$HOME/bin/procman"
    fi
else
    # ~/.local/bin not in PATH; check ~/bin
    if [[ -n "$(path_index ~/bin)" ]]; then
        primary_target="$HOME/bin/procman"
    else
        # Neither is in PATH: loop over all PATH entries.
        local best_target=""
        for dir in $PATH; do
            if ! [[ -d "$dir" ]]; then
                continue
            fi
            if mkdir -p "$dir/procman" 2>/dev/null; then
                best_target="$dir/procman"
                break
            fi
        done
        primary_target="$best_target"
    fi
fi

# If we couldn't find any suitable target, fail.
if [[ -z "$primary_target" ]]; then
    print_error "No writable directory found in PATH to install Procman."
    print_error "Please ensure ~/.local/bin or ~/bin (or another writable directory) is in your PATH, or run this script with sudo."
    exit 1
fi

# Attempt installation.
if ! try_install "$primary_target"; then
    exit 1
fi

print_info "Installation complete."
