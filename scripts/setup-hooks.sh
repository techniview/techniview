#!/bin/bash
set -e
echo "Setting up TechniView pre-commit hooks..."

# Use tracked .githooks so hooks are versioned and shared
git config core.hooksPath .githooks
echo "  ok: core.hooksPath = .githooks (tracked, no install needed)"

# Keep setup deterministic: dependencies are installed by `make install`, not by
# a git hook or helper script running implicitly during a commit.
if ! command -v uv >/dev/null 2>&1; then
  echo "  uv is missing; install uv and run 'make install'."
  exit 1
fi

echo "Done. Hooks run on every git commit via .githooks/pre-commit."
