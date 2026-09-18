# shellcheck shell=bash disable=SC2034

# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

# Sourced by action.yml and pitloom-install.sh; not run directly.
#
# Sets python_bin to the first of python, python3 that exists and runs (a
# Windows Store stub exists on PATH but fails to run), or to "" if none.
# "python" goes first: it is the name a setup-python step or a venv provides
# on every OS, and the only one on Windows.
#
# Also defines:
#   require_python  exit 1 with an ::error:: annotation if python_bin is empty
#   python_text     run python_bin with UTF-8 stdio and without the CR that
#                   Windows Python adds to every line, so that $(...) and
#                   readarray-style captures get clean text
#
# See also: python_probe.py, pitloom-install.sh

python_bin=""
for candidate in python python3; do
  if command -v "${candidate}" >/dev/null 2>&1 \
    && "${candidate}" -c 'pass' >/dev/null 2>&1; then
    python_bin="${candidate}"
    break
  fi
done

require_python() {
  if [ -z "${python_bin}" ]; then
    echo "::error::No working python found on PATH"
    exit 1
  fi
}

python_text() {
  if [ -z "${python_bin}" ]; then
    echo "No working python found on PATH" >&2
    return 127
  fi
  PYTHONIOENCODING=utf-8 "${python_bin}" "$@" | tr -d '\r'
}
