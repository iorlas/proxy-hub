package compose.images

# Docker Compose image policy.
# Enforces: no build directives, mutable tags require pull_policy: always.
#
# OWN_IMAGE_PREFIX-based SHA pinning is handled via data injection:
#   conftest test --data '{"own_image_prefix": "ghcr.io/myorg/"}' ...

import rego.v1

# ── Policy: no build directives ──

deny contains msg if {
	some name, svc in input.services
	svc.build
	msg := sprintf("services.%s: has 'build:' directive — pre-build images in CI, never on the server", [name])
}

# ── Policy: mutable third-party tags require pull_policy: always ──
# Includes images with NO tag (implicit :latest — I0125 bug fix)

mutable_tags := {":latest", ":main", ":master", ":dev"}

deny contains msg if {
	some name, svc in input.services
	image := svc.image

	some tag in mutable_tags
	endswith(image, tag)

	not _is_own_image(image)

	not svc.pull_policy == "always"
	msg := sprintf("services.%s: mutable tag '%s' requires 'pull_policy: always'", [name, image])
}

# Images with NO tag at all default to :latest implicitly
deny contains msg if {
	some name, svc in input.services
	image := svc.image

	# No colon means no tag — implicit :latest
	not contains(image, ":")

	not _is_own_image(image)

	not svc.pull_policy == "always"
	msg := sprintf("services.%s: image '%s' has no tag (defaults to :latest) — add explicit tag or set 'pull_policy: always'", [name, image])
}

# ── Policy: own images must be pinned ──

deny contains msg if {
	prefix := data.own_image_prefix
	prefix != ""

	some name, svc in input.services
	image := svc.image
	startswith(image, prefix)

	# Extract tag
	tag := _get_tag(image)

	# Reject mutable tags
	unpinned_tags := {"latest", "main", "master", "dev", ""}
	tag in unpinned_tags

	msg := sprintf("services.%s: own image '%s' must use a pinned tag (e.g., main-abc1234 or @sha256:...), not '%s'", [name, image, tag])
}

# ── Helpers ──

_is_own_image(image) if {
	prefix := data.own_image_prefix
	startswith(image, prefix)
}

_get_tag(image) := tag if {
	parts := split(image, ":")
	count(parts) > 1
	tag := parts[count(parts) - 1]
} else := ""
