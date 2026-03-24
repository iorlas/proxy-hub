package gitignore.secrets

# .gitignore policy: ensure secrets and build artifacts are ignored.
# Prevents agents from accidentally committing .env files, venvs, or coverage data.
#
# Input: array of [{Kind, Value, Original}] entries
# Parser: --parser ignore

import rego.v1

# Critical entries that must be in .gitignore
required_patterns := [".env", ".venv", "__pycache__"]

# ── Policy: critical patterns must be gitignored ──

deny contains msg if {
	some pattern in required_patterns
	not _pattern_present(pattern)
	msg := sprintf(".gitignore: '%s' is not ignored — agents may accidentally commit secrets or artifacts", [pattern])
}

_pattern_present(pattern) if {
	some entry in input
	entry.Kind == "Path"
	contains(entry.Value, pattern)
}
