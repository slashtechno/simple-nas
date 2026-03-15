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

# Append a [/drives] volume over /host/mnt unless the template already defines
# one. The drive containing FILES_DIR is hidden from the browser listing via
# unlist so its content doesn't appear twice.
# Note: unlist is browser-UI only and does not affect WebDAV.
if ! grep -q '^\[/drives\]' /cfg/copyparty.conf; then
    _host_mnt="${HOST_MNT_DIR:-/mnt}"
    _files_rel="${FILES_DIR#${_host_mnt}/}"  # e.g. t7/files
    _files_drive="${_files_rel%%/*}"          # e.g. t7
    printf '\n[/drives]\n  /host/mnt\n  accs:\n    r: %s\n  flags:\n    -e2d\n    unlist: ^%s(/|$)\n' \
        "$COPYPARTY_USER" "$_files_drive" >> /cfg/copyparty.conf
fi

# Run copyparty with the config file
exec python3 -m copyparty -c /cfg/copyparty.conf
