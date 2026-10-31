ARG DEBIAN_IMAGE=debian:trixie-slim@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad
ARG DEBIAN_SNAPSHOT=20261029T235959Z

FROM ${DEBIAN_IMAGE} AS go-judge-build
ARG DEBIAN_SNAPSHOT
RUN printf '%s\n' \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/ trixie main" \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/ trixie-updates main" \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}/ trixie-security main" \
      > /etc/apt/sources.list \
    && rm -f /etc/apt/sources.list.d/debian.sources
RUN test "$(dpkg --print-architecture)" = amd64 && apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://github.com/criyle/go-judge/releases/download/v1.13.3/go-judge_1.13.3_linux_amd64 -o /go-judge \
    && echo '509782f8959987256d99ac6dc8062ec593d776f291401c8e0c28bdc48dcd1880  /go-judge' | sha256sum -c - \
    && chmod 755 /go-judge

FROM ${DEBIAN_IMAGE} AS python-build
ARG DEBIAN_SNAPSHOT
ARG PYTHON_VERSION=3.14.8
ARG PYTHON_SHA256=c2215904f02b175596dc49351585104f4bc20341e1c47378b26a2c274360ce73
RUN printf '%s\n' \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/ trixie main" \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/ trixie-updates main" \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}/ trixie-security main" \
      > /etc/apt/sources.list \
    && rm -f /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates xz-utils pkg-config \
    libbz2-dev libffi-dev liblzma-dev libreadline-dev libsqlite3-dev libssl-dev \
    libncurses-dev uuid-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tar.xz" -o /tmp/python.tar.xz \
    && echo "${PYTHON_SHA256}  /tmp/python.tar.xz" | sha256sum -c - \
    && mkdir /tmp/python && tar -xf /tmp/python.tar.xz -C /tmp/python --strip-components=1 \
    && cd /tmp/python \
    && ./configure --prefix=/opt/python --without-ensurepip --disable-test-modules \
    && make -j4 && make install \
    && install -Dm644 LICENSE /opt/python/LICENSE \
    && rm -rf /opt/python/include /opt/python/lib/libpython*.a /tmp/python /tmp/python.tar.xz
RUN strip /opt/python/bin/python3.14 /opt/python/lib/python3.14/lib-dynload/*.so \
    && find /opt/python -type d -name __pycache__ -prune -exec rm -rf '{}' + \
    && rm -rf /opt/python/lib/pkgconfig /opt/python/lib/python3.14/config-* \
      /opt/python/lib/python3.14/ensurepip /opt/python/lib/python3.14/idlelib \
      /opt/python/lib/python3.14/turtledemo

FROM ${DEBIAN_IMAGE}
ARG DEBIAN_SNAPSHOT
RUN printf '%s\n' \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/ trixie main" \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT}/ trixie-updates main" \
      "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT}/ trixie-security main" \
      > /etc/apt/sources.list \
    && rm -f /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    libbz2-1.0 libffi8 liblzma5 libreadline8t64 libsqlite3-0 libssl3t64 \
    libncursesw6 libuuid1 zlib1g \
    && rm -rf /var/lib/apt/lists/*
COPY --from=python-build /opt/python /opt/python
COPY --from=go-judge-build /go-judge /usr/local/bin/go-judge
COPY --from=go-judge-build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
RUN mkdir -p /usr/lib/ssl \
    && ln -sf /etc/ssl/certs/ca-certificates.crt /usr/lib/ssl/cert.pem \
    && ln -sf /etc/ssl/certs /usr/lib/ssl/certs
COPY go-judge-mount.yaml /etc/go-judge-mount.yaml
CMD ["sh", "-c", "exec go-judge -http-addr 0.0.0.0:5050 -no-fallback -container-cred-start 1536 -mount-conf /etc/go-judge-mount.yaml -parallelism ${GO_JUDGE_PARALLELISM:-16} -output-limit 4m -copy-out-limit 4m -src-prefix /opt/python"]
