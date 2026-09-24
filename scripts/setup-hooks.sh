#!/bin/bash
set -e
echo "Setting up TechniView pre-commit hooks..."

# Use tracked .githooks so hooks are versioned and shared
git config core.hooksPath .githooks
echo "  ok: core.hooksPath = .githooks (tracked, no install needed)"

# Keep setup deterministic: dependencies are installed by `make install`, not by
# a git hook or helper script running implicitly during a commit.
if ! command -v pre-commit >/dev/null 2>&1; then
  echo "  pre-commit is missing; run 'make install' to install it."
  exit 1
fi

echo "Done. Hooks run on every git commit via .githooks/pre-commit."
