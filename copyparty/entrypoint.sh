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

# Run copyparty with the config file
exec python3 -m copyparty -c /cfg/copyparty.conf
