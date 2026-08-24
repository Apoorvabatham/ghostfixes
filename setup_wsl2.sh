#!/usr/bin/env bash
# One-time setup for GhostFixes. Run inside the WSL2 (Ubuntu) terminal.
# Requires sudo — you'll be prompted for your WSL2 password.
#
# bubblewrap, socat, node, the Claude Code CLI, and the sandbox seccomp filter
# are already installed system-wide from the previous project — this script only
# adds what GhostFixes needs on top.
set -euo pipefail

echo "== Installing exiftool (required by Stage 0 item 6: EXIF survival check) =="
sudo apt-get update
sudo apt-get install -y libimage-exiftool-perl

echo
echo "== Verifying =="
exiftool -ver
python3 --version
bwrap --version
socat -V 2>&1 | head -1
claude --version

echo
echo "Setup complete."
