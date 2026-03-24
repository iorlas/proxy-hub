package compose.hostname

# Docker Compose hostname policy.
# Enforces: services on dokploy-network must set hostname.
#
# dokploy-network is the shared platform network — being on it means the service
# is exposed to all other compose projects. hostname is the DNS contract.
# Services that don't need cross-project discovery should use an internal network
# (internal: true) instead of dokploy-network.

import rego.v1

# ── Policy: services on dokploy-network must have hostname ──

deny contains msg if {
	some name, svc in input.services
	not svc.hostname

	# Only applies to services on dokploy-network
	_on_dokploy_network(svc)

	# Skip one-shot services
	not _is_one_shot(name)

	msg := sprintf("services.%s: missing 'hostname:' — dokploy-network means exposed; set hostname (DNS contract) or move to an internal network", [name])
}

# ── Helpers ──

_on_dokploy_network(svc) if {
	some net in svc.networks
	net == "dokploy-network"
}

_on_dokploy_network(svc) if {
	is_object(svc.networks)
	svc.networks["dokploy-network"]
}

_is_one_shot(name) if {
	some _, other_svc in input.services
	deps := other_svc.depends_on
	is_object(deps)
	dep := deps[name]
	dep.condition == "service_completed_successfully"
}
