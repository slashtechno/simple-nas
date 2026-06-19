#!/bin/sh
set -e

# Determine which template to use
# 1. Custom template in the config volume (mapped to /cfg)
# 2. Default template baked into the image
if [ -f /cfg/copyparty.conf.template ]; then
    TEMPLATE_FILE="/cfg/copyparty.conf.template"
    echo "Using custom configuration template: $TEMPLATE_FILE"
else
    TEMPLATE_FILE="/etc/copyparty/copyparty.conf.template.default"
    echo "Using default configuration template: $TEMPLATE_FILE"
fi

# Render config file from template
# Using | as delimiter to avoid issues with / in passwords
sed -e "s|\${COPYPARTY_USER}|$COPYPARTY_USER|g" \
    -e "s|\${COPYPARTY_PASS}|$COPYPARTY_PASS|g" \
    "$TEMPLATE_FILE" > /cfg/copyparty.conf

# Append a [/drives] section unless the template already defines one.
# Uses an empty backing directory as the parent so WebDAV never sees the raw
# /host/mnt listing. Each drive under HOST_MNT_DIR gets its own sub-volume,
# except the one containing FILES_DIR (which is already exposed at [/]).
if ! grep -q '^\[/drives\]' /cfg/copyparty.conf; then
    _host_mnt="${HOST_MNT_DIR:-/mnt}"
    _files_rel="${FILES_DIR#${_host_mnt}/}"  # e.g. t7/files
    _files_drive="${_files_rel%%/*}"          # e.g. t7

    # Empty parent dir — sub-volumes below appear in its listing without
    # exposing any real filesystem path at the /drives level itself.
    mkdir -p /tmp/drives-root
    printf '\n[/drives]\n  /tmp/drives-root\n  accs:\n    r: %s\n  flags:\n    -e2d\n' \
        "$COPYPARTY_USER" >> /cfg/copyparty.conf

    # One sub-volume per drive, skipping the one that contains FILES_DIR.
    for _dir in /host/mnt/*/; do
        [ -d "$_dir" ] || continue
        _name="${_dir%/}"
        _name="${_name##*/}"
        if [ "$_name" != "$_files_drive" ]; then
            printf '\n[/drives/%s]\n  %s\n  accs:\n    r: %s\n  flags:\n    -e2d\n' \
                "$_name" "$_dir" "$COPYPARTY_USER" >> /cfg/copyparty.conf
        fi
    done
fi

# Run copyparty with the config file
exec python3 -m copyparty -c /cfg/copyparty.conf
