# Caddy with two plugins the stock images lack: caddy-docker-proxy (routes by container label) and the
# Cloudflare DNS plugin (Let's Encrypt certificates for names that are not reachable from the internet).
# The versions are in group_vars/all/versions.yml.
ARG CADDY_VERSION
FROM caddy:${CADDY_VERSION}-builder AS builder
ARG CADDY_VERSION
ARG CADDY_DOCKER_PROXY_VERSION
ARG CADDY_CLOUDFLARE_DNS_VERSION
RUN xcaddy build v${CADDY_VERSION} \
    --with github.com/lucaslorentz/caddy-docker-proxy/v2@v${CADDY_DOCKER_PROXY_VERSION} \
    --with github.com/caddy-dns/cloudflare@v${CADDY_CLOUDFLARE_DNS_VERSION}

FROM caddy:${CADDY_VERSION}-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
CMD ["caddy", "docker-proxy"]
