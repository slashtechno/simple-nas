#!/usr/bin/env bash
# Runs the plugin generator (update_plugins.yml) on a copy of the tracked files, with no network and no vault: the template and every
# plugin in plugins/ are scanned, and plugins.yml must parse, keep the {{ }} of an entry as text, sort the entries by key, and
# resolve through Ansible's own loader. Then each mistake a plugin author can make must fail with a message naming it.
set -euo pipefail
cd "$(dirname "$0")/.."
source_dir="$PWD"

work="$(mktemp -d)"
trap '[ -n "${KEEP:-}" ] || rm -rf "$work"' EXIT
mkdir -p "$work/group_vars/all" "$work/host_vars" "$work/plugins" "$work/tests"
for f in "$source_dir"/group_vars/all/*; do
  case "$f" in */vars.yml | */vault.yml | */plugins.yml) ;; *) cp "$f" "$work/group_vars/all/" ;; esac
done
cp "$source_dir/ansible.cfg" "$source_dir/update_plugins.yml" "$work/"
cp "$source_dir/tests/check_keys.yml" "$work/tests/"
cp "$source_dir/host_vars/vars.yml.example" "$work/host_vars/"
cp -R "$source_dir/roles" "$work/roles"
cp -R "$source_dir/plugin-template" "$work/plugins/zzz"
for d in "$source_dir"/plugins/*/; do [ -d "$d" ] && cp -R "$d" "$work/plugins/$(basename "$d")"; done || true
# The template as a second plugin, named to sort first, with an entry that holds a template and an oidc client.
cp -R "$source_dir/plugin-template" "$work/plugins/aaa"
sed -i.bak -e 's/example/aaa/g' -e 's/Example/Aaa/' "$work/plugins/aaa/service.yml" "$work/plugins/aaa/defaults.yml" "$work/plugins/aaa/defaults/main.yml"
sed -i.bak -e 's/example/zzz/g' -e 's/Example/Zzz/' "$work/plugins/zzz/service.yml" "$work/plugins/zzz/defaults.yml" "$work/plugins/zzz/defaults/main.yml"
printf '%s\n' "data: [aaa_data_dir, \"{{ 'aaa_data_dir' if aaa_enabled | bool else '' }}\"]" >> "$work/plugins/aaa/service.yml"
sed -i.bak '/^data: \[aaa_data_dir\]$/d' "$work/plugins/aaa/service.yml"
find "$work/plugins" -name '*.bak' -delete
cd "$work"

run() { ansible-playbook update_plugins.yml "$@" 2>&1; }
ok=$(run) || { echo "$ok" >&2; echo "FAIL: the generator failed on the template and the committed plugins" >&2; exit 1; }
[ -n "${KEEP:-}" ] && { echo "$work" >&2; echo "$ok" | tail -15 >&2; }
[ -f group_vars/all/plugins.yml ] || { echo "FAIL: plugins.yml was not written" >&2; exit 1; }
grep -q "if aaa_enabled | bool" group_vars/all/plugins.yml || { echo "FAIL: the {{ }} in an entry did not survive" >&2; exit 1; }
rm -f group_vars/all/plugins.yml.bak

value() { ansible localhost -m ansible.builtin.debug -a "msg={{ $1 | string }}" 2>/dev/null | sed -n 's/.*"msg": "\(.*\)".*/\1/p'; }
keys="$(value "plugin_services | map(attribute='key') | join(',')")"
case "$keys" in aaa,*,zzz | aaa,zzz) echo "ok: entries sorted by key ($keys)" ;; *) echo "FAIL: entries are '$keys'" >&2; exit 1 ;; esac
[ "$(value "services | map(attribute='key') | select('in', ['aaa', 'zzz', 'immich']) | list | length")" = 3 ] || { echo "FAIL: services misses a plugin" >&2; exit 1; }
[ "$(value "aaa_enabled")" = False ] || { echo "FAIL: a plugin's flag is not read from plugins.yml" >&2; exit 1; }
echo "ok: plugins.yml loads with the core's settings"

fails() {   # fails <text of the message> <what the mistake is>; the test restores the plugin afterwards
  local out
  if out=$(run); then echo "FAIL: the generator accepted $2" >&2; exit 1; fi
  case "$out" in *"$1"*) echo "ok: $2 is refused" ;; *) echo "$out" >&2; echo "FAIL: no message with '$1' for $2" >&2; exit 1 ;; esac
}
cp plugins/aaa/defaults.yml /tmp/aaa-defaults.$$
printf '%s\n' 'timezone: Europe/Paris' >> plugins/aaa/defaults.yml
fails "already declared in another file" "a plugin setting the core declares"
cp /tmp/aaa-defaults.$$ plugins/aaa/defaults.yml
sed -i.bak 's/^aaa_enabled: false/aaa_enabled: true/' plugins/aaa/defaults.yml
fails "must default to false" "a flag that defaults to true"
cp /tmp/aaa-defaults.$$ plugins/aaa/defaults.yml
sed -i.bak '/^aaa_subdomain/d' plugins/aaa/defaults.yml
fails "needs aaa_subdomain" "a web service without a subdomain"
cp /tmp/aaa-defaults.$$ plugins/aaa/defaults.yml
rm -f plugins/aaa/defaults.yml.bak /tmp/aaa-defaults.$$
mv plugins/zzz plugins/zzy
fails "the folder is named zzy" "a folder named differently from its key"
mv plugins/zzy plugins/zzz
mkdir plugins/roles_dup && cp plugins/zzz/service.yml plugins/zzz/defaults.yml plugins/roles_dup/ && mkdir plugins/roles_dup/tasks && cp plugins/zzz/tasks/main.yml plugins/roles_dup/tasks/
fails "is used twice" "two plugin folders with one key"
rm -rf plugins/roles_dup
printf '%s\n' 'aaa_typo: 1' > group_vars/all/vars.yml
fails "aaa_typo" "a setting no plugin declares in vars.yml"
printf '%s\n' 'aaa_port: 8080' > group_vars/all/vars.yml
run >/dev/null || { echo "FAIL: a plugin's own setting in vars.yml was refused" >&2; exit 1; }
echo "ok: a plugin's setting in vars.yml is accepted"
printf '%s\n' 'plugins: [{key: x, location: "http://example.com/x", commit: "0000000000000000000000000000000000000000"}]' > group_vars/all/vars.yml
fails "The plugins entry" "a plugin location that is not https"
printf '%s\n' 'plugins: [{key: x, location: "https://example.com/x", commit: v1.0.0}]' > group_vars/all/vars.yml
fails "The plugins entry" "a tag instead of a commit hash"
printf '%s\n' 'plugins: [{key: x, location: "https://example.com/x", commit: abc1234}]' > group_vars/all/vars.yml
fails "The plugins entry" "a short hash instead of the full commit hash"
