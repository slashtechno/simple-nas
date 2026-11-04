#!/usr/bin/env bash
# Checks the order Ansible loads group_vars/all and host_vars with the real loader: the tracked defaults first, then
# the owner's vars.yml, then versions.yml (which the owner cannot override), and a host's own vars last of the three.
# Runs on a copy of the tracked files, so it needs no vault and touches nothing real.
set -euo pipefail
cd "$(dirname "$0")/.."
source_dir="$PWD"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/group_vars/all" "$work/host_vars/h"
for f in "$source_dir"/group_vars/all/*.yml; do
  case "$f" in */vars.yml | */vault.yml) ;; *) cp "$f" "$work/group_vars/all/" ;; esac
done
# The owner's file overrides a default (timezone), sets a flag, and tries to override a version (which must not win).
printf '%s\n' 'timezone: Owner/Zone' 'gitea_enabled: true' 'caddy_version: 0.0.0-owner' > "$work/group_vars/all/vars.yml"
printf '%s\n' 'timezone: Host/Zone' > "$work/host_vars/h/vars.yml"
cd "$work"   # ad-hoc ansible also loads group_vars from the current directory
printf '%s\n' 'all: {hosts: {h: {ansible_connection: local}, g: {ansible_connection: local}}}' > "$work/hosts.yml"

value() { ansible -i hosts.yml "$1" -m ansible.builtin.debug -a "msg={{ $2 | string }}" | sed -n 's/.*"msg": "\(.*\)".*/\1/p'; }
expect() {
  local got
  got="$(value "$1" "$2")"
  [ "$got" = "$3" ] || { echo "FAIL: $2 on $1 is '$got', expected '$3'" >&2; exit 1; }
  echo "ok: $2 on $1 is $3"
}

expect g docker_network services         # a tracked default nobody overrode
expect g timezone Owner/Zone             # vars.yml beats the tracked default
expect h timezone Host/Zone              # host_vars beat vars.yml
expect g gitea_enabled True              # vars.yml beats the flag's default (false)
expect g caddy_version "$(sed -n 's/^caddy_version: *//p' $source_dir/group_vars/all/versions.yml)"   # versions.yml loads last
