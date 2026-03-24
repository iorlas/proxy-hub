package dockerfile.secrets

# Dockerfile secrets policy.
# Detects sensitive values passed via ENV or ARG instructions.
# Agents frequently hardcode API keys and passwords in Dockerfiles.
# Derived from Trivy DS-0031 / Rally Health CTNRSEC-0002.
#
# Input: flat array of Dockerfile instructions [{Cmd, Flags, Value, Stage}, ...]

import rego.v1

# Suspicious key patterns (case-insensitive matching via regex)
secret_patterns := [
	"password",
	"passwd",
	"secret",
	"api_key",
	"apikey",
	"api.key",
	"access_key",
	"access_token",
	"auth_token",
	"private_key",
	"token",
	"credential",
]

# ── Policy: no secrets in ENV ──

deny contains msg if {
	some instr in input
	instr.Cmd == "env"
	some val in instr.Value

	# ENV can be "KEY=value" or just "KEY value"
	key := _extract_env_key(val)
	_is_secret_key(key)

	msg := sprintf("ENV '%s' looks like a secret — never bake secrets into images. Use runtime env vars or mounted secrets.", [key])
}

# ── Policy: no secrets in ARG ──

deny contains msg if {
	some instr in input
	instr.Cmd == "arg"
	some val in instr.Value

	key := _extract_arg_key(val)
	_is_secret_key(key)

	msg := sprintf("ARG '%s' looks like a secret — build args are visible in image history. Use runtime env vars or mounted secrets.", [key])
}

# ── Helpers ──

_extract_env_key(val) := key if {
	contains(val, "=")
	key := split(val, "=")[0]
} else := val

_extract_arg_key(val) := key if {
	contains(val, "=")
	key := split(val, "=")[0]
} else := val

_is_secret_key(key) if {
	some pattern in secret_patterns
	regex.match(sprintf("(?i)%s", [pattern]), key)
}
