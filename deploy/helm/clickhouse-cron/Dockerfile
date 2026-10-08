# Builds the cron-sidecar image referenced by podTemplate.sidecars in
# ../clickhouse-helm-chart/values.yaml. Runs supercronic -- a cron-compatible
# scheduler that logs job output to stdout instead of silently discarding it
# like a plain crond -- as a persistent sidecar alongside the ClickHouse
# container, driving the scripts in ./scripts.
#
# Build (multi-arch) and push:
#   docker buildx build --platform linux/amd64,linux/arm64 \
#     -t your-registry/clickhouse-cron:latest --push .
#
# Then point podTemplate.sidecars[0].image in values.yaml at the pushed tag.

FROM alpine:3.20 AS builder

ARG SUPERCRONIC_VERSION=v0.2.49
ARG TARGETARCH

# supercronic publishes no official checksum file; these sha256 sums were
# computed by hand against the v0.2.49 release assets. Recompute both if
# SUPERCRONIC_VERSION changes.
ARG SUPERCRONIC_SHA256_AMD64=a53ae236602c7338aba3fbaff40bda6300eae3b9fedb8261eb06cfe3724430c1
ARG SUPERCRONIC_SHA256_ARM64=02aa0cb229ba09050cba6638059dadb9eedc2276632ea43d6a57a2f8c1629dd5

RUN apk add --no-cache curl && \
    case "${TARGETARCH}" in \
      amd64) BIN=supercronic-linux-amd64; SHA="${SUPERCRONIC_SHA256_AMD64}" ;; \
      arm64) BIN=supercronic-linux-arm64; SHA="${SUPERCRONIC_SHA256_ARM64}" ;; \
      *) echo "unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
    esac && \
    curl -fsSLo /tmp/supercronic "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/${BIN}" && \
    echo "${SHA}  /tmp/supercronic" | sha256sum -c - && \
    chmod +x /tmp/supercronic

FROM alpine:3.20

RUN apk add --no-cache ca-certificates bash

COPY --from=builder /tmp/supercronic /usr/local/bin/supercronic
COPY scripts/ /opt/scripts/
RUN chmod +x /opt/scripts/*.sh

# No ENTRYPOINT/CMD: podTemplate.sidecars[0].command in values.yaml writes
# the crontab at startup and execs supercronic directly, so the schedule
# lives in one place (values.yaml) instead of being baked into the image.
