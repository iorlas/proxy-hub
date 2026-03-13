# Stage 1: Build g3proxy from source
FROM rust:bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    libclang-dev cmake capnproto \
    && rm -rf /var/lib/apt/lists/*

# Clone and build g3proxy
RUN git clone --depth 1 https://github.com/bytedance/g3.git /build
WORKDIR /build

RUN cargo build --profile release-lto -p g3proxy \
    --no-default-features \
    --features vendored-openssl,vendored-c-ares

# Stage 2: Runtime
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    gettext-base ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/target/release-lto/g3proxy /usr/bin/g3proxy

RUN mkdir -p /etc/g3proxy /var/cache/g3proxy

COPY config/g3proxy.yaml.tmpl /etc/g3proxy/g3proxy.yaml.tmpl
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
