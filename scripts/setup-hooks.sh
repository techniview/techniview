#!/bin/bash
set -e
echo "Setting up TechniView pre-commit hooks..."

# Use tracked .githooks so hooks are versioned and shared
git config core.hooksPath .githooks
echo "  ok: core.hooksPath = .githooks (tracked, no install needed)"

# Ensure pre-commit is available for the wrapper to call
if ! command -v pre-commit >/dev/null 2>&1; then
  echo "  Installing pre-commit..."
  if command -v pipx >/dev/null 2>&1; then
    pipx install pre-commit
  else
    pip install --break-system-packages -q pre-commit
  fi
fi

echo "Done. Hooks run on every git commit via .githooks/pre-commit."
