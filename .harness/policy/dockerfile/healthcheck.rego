package dockerfile.healthcheck

# Dockerfile HEALTHCHECK policy.
# Ensures at least one HEALTHCHECK instruction exists.
# Without it, orchestrators can't detect unhealthy containers.
# Derived from CIS Docker Benchmark 4.6 / Trivy DS-0026.
#
# Input: flat array of Dockerfile instructions [{Cmd, Flags, Value, Stage}, ...]

import rego.v1

# ── Policy: must have HEALTHCHECK instruction ──

deny contains msg if {
	not _has_healthcheck
	msg := "Dockerfile has no HEALTHCHECK instruction — orchestrators can't detect unhealthy containers. Add 'HEALTHCHECK CMD curl -f http://localhost/ || exit 1' or similar."
}

_has_healthcheck if {
	some instr in input
	instr.Cmd == "healthcheck"
}
