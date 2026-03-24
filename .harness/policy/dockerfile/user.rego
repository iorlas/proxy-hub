package dockerfile.user

# Dockerfile USER policy.
# Ensures at least one USER instruction exists (non-root).
# Derived from CIS Docker Benchmark 4.1.
#
# Input: flat array of Dockerfile instructions [{Cmd, Flags, Value, Stage}, ...]

import rego.v1

# ── Policy: must have USER instruction ──

deny contains msg if {
	not _has_user_instruction
	msg := "Dockerfile has no USER instruction — containers should not run as root. Add 'USER nonroot' or similar."
}

_has_user_instruction if {
	some instr in input
	instr.Cmd == "user"
}
