#!/bin/sh
# Initial public Python/SSH bootstrap. No private repositories, SSH connections or board commands.
set -eu
supported_python() {
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys;raise SystemExit(not ((3,11)<=sys.version_info[:2]<(3,14)))' >/dev/null 2>&1; then
      printf '%s\n' "$candidate"; return 0
    fi
  done
  return 1
}
if supported_python >/dev/null 2>&1 && command -v ssh >/dev/null 2>&1; then exit 0; fi
if [ "$(uname -s)" != Linux ]; then
  echo 'Automatic public prerequisite setup supports Linux package managers and Windows PowerShell.' >&2; exit 1
fi
# Preserve existing sudo policy. Never request interactive credentials from an automated launcher.
if [ "$(id -u)" -eq 0 ]; then
  privilege() { "$@"; }
else
  privilege() { sudo -n "$@"; }
fi
if command -v apt-get >/dev/null 2>&1; then
  if supported_python >/dev/null 2>&1; then
    privilege apt-get install -y openssh-client
  else
    privilege apt-get install -y python3 python3-venv openssh-client
  fi
elif command -v dnf >/dev/null 2>&1; then
  if supported_python >/dev/null 2>&1; then
    privilege dnf install -y openssh-clients
  else
    privilege dnf install -y python3 python3-pip openssh-clients
  fi
elif command -v pacman >/dev/null 2>&1; then
  privilege pacman -S --needed --noconfirm python python-pip openssh
else
  echo 'No supported OS package manager was found. Supply a supported Python 3.11-3.13 installation.' >&2; exit 1
fi
supported_python >/dev/null || { echo 'A supported Python remains unavailable from this OS package repository.' >&2; exit 1; }
command -v ssh >/dev/null 2>&1 || { echo 'OpenSSH client remains unavailable.' >&2; exit 1; }
