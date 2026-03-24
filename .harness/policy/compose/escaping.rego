package compose.escaping

# Docker Compose environment variable escaping policy.
# Detects bare $ in environment values that Docker Compose will interpolate.
#
# Docker Compose interpolates $VAR and ${VAR} in values. A bare $ (common in
# bcrypt hashes like $2a$12$..., or passwords with special chars) will be
# silently interpreted as a variable reference, corrupting the value.
# Must be escaped as $$ in compose files.

import rego.v1

# ── Policy: bare $ in environment values ──

deny contains msg if {
	some name, svc in input.services
	env := svc.environment
	is_object(env)

	some key, val in env
	is_string(val)
	_has_bare_dollar(val)

	msg := sprintf("services.%s: environment.%s contains bare '$' — Docker Compose will interpolate this as a variable. Escape as '$$' if literal (e.g., bcrypt hashes, special chars).", [name, key])
}

# Also check environment as list format: ["KEY=value"]
deny contains msg if {
	some name, svc in input.services
	env := svc.environment
	is_array(env)

	some entry in env
	is_string(entry)
	contains(entry, "=")
	parts := split(entry, "=")
	key := parts[0]

	# Rejoin everything after first = (value may contain =)
	val := substring(entry, count(key) + 1, -1)
	_has_bare_dollar(val)

	msg := sprintf("services.%s: environment %s contains bare '$' — Docker Compose will interpolate this as a variable. Escape as '$$' if literal.", [name, key])
}

# True if string contains $ not followed by { or $ or end-of-string
_has_bare_dollar(s) if {
	# Match $ followed by a word character (variable interpolation pattern)
	regex.match(`\$[a-zA-Z0-9_]`, s)

	# But not already escaped as $$ or used as ${VAR}
	not regex.match(`^(\$\{|\$\$)`, s)
}
