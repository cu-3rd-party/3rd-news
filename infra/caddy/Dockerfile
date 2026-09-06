FROM golang:1.26.7-alpine@sha256:28d89ee9cc0ff9fec75c82ca201e6bf7fdf9a679d4b7b24dfa04f2bb766bb468 AS build

WORKDIR /src
ENV CGO_ENABLED=0

COPY infra/caddy/go.mod infra/caddy/go.sum ./
RUN go mod download

COPY infra/caddy/main.go ./
RUN go build \
    -buildvcs=false \
    -trimpath \
    -ldflags="-s -w" \
    -o /out/caddy \
    .

FROM alpine:3.23.5@sha256:fd791d74b68913cbb027c6546007b3f0d3bc45125f797758156952bc2d6daf40 AS runtime

COPY --from=build --chmod=0755 /out/caddy /usr/bin/caddy

RUN apk upgrade --no-cache \
    && apk add --no-cache ca-certificates libcap \
    && setcap cap_net_bind_service=+ep /usr/bin/caddy \
    && apk del libcap \
    && addgroup -S caddy \
    && adduser -S -D -H -h /var/lib/caddy -s /sbin/nologin -G caddy caddy \
    && mkdir -p /config/caddy /data/caddy /etc/caddy /srv /var/lib/caddy \
    && chown -R caddy:caddy /config /data /var/lib/caddy

ENV XDG_CONFIG_HOME=/config \
    XDG_DATA_HOME=/data

WORKDIR /srv
USER caddy

EXPOSE 80 443 443/udp 2019
VOLUME ["/config", "/data"]

ENTRYPOINT ["caddy"]
CMD ["run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]


FROM oven/bun:1.4.2-alpine@sha256:d888c0ae6c86d7866ff10c5aafdd9077b36aee6455b33dd270fb93c0dd5cef6f AS web-build
WORKDIR /build/apps/web
COPY apps/web/package.json apps/web/bun.lock ./
RUN bun install --frozen-lockfile
COPY apps/web/ ./
RUN bun run build

FROM runtime AS web
COPY apps/web/Caddyfile /etc/caddy/Caddyfile
COPY --from=web-build /build/apps/web/dist /srv
