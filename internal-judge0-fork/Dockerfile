FROM debian:trixie-slim AS go-judge-build
RUN test "$(dpkg --print-architecture)" = amd64 && apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://github.com/criyle/go-judge/releases/download/v1.13.3/go-judge_1.13.3_linux_amd64 -o /go-judge \
    && echo '509782f8959987256d99ac6dc8062ec593d776f291401c8e0c28bdc48dcd1880  /go-judge' | sha256sum -c - \
    && chmod 755 /go-judge

FROM ruby:3.4-slim-trixie@sha256:c12225b6a73743f943530d9e610f4ae78e0dbcffdcf797b01522a55f7d25acb3 AS runtime
ENV RAILS_ENV=production \
    BUNDLE_PATH=/opt/bundle \
    BUNDLE_DEPLOYMENT=1 \
    BUNDLE_WITHOUT=development:test \
    JUDGE0_VERSION=techniview-python-1
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --create-home judge0
WORKDIR /api

FROM runtime AS gems
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libyaml-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
COPY api/Gemfile api/Gemfile.lock ./
RUN bundle install --jobs 4 && rm -rf /opt/bundle/ruby/*/cache

FROM runtime AS api
COPY --from=gems /opt/bundle /opt/bundle
COPY api/ /api/
COPY languages/active.rb /api/db/languages/active.rb
COPY LICENSE /api/LICENSE
RUN mkdir -p /api/tmp/pids /api/log \
    && chown -R judge0:judge0 /api/tmp /api/log \
    && chmod 755 /api/docker-entrypoint.sh /api/scripts/server /api/scripts/workers
USER judge0
EXPOSE 2358
ENTRYPOINT ["/api/docker-entrypoint.sh"]
CMD ["/api/scripts/server"]

FROM runtime AS sandbox-build
ARG PYTHON_VERSION=3.14.8
ARG PYTHON_SHA256=c2215904f02b175596dc49351585104f4bc20341e1c47378b26a2c274360ce73
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl xz-utils pkg-config libcap-dev libseccomp-dev \
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
FROM api AS worker
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcap2 libseccomp2 libbz2-1.0 libffi8 liblzma5 libreadline8t64 libsqlite3-0 \
    libssl3t64 libncursesw6 libuuid1 zlib1g util-linux procps \
    && rm -rf /var/lib/apt/lists/*
COPY --from=sandbox-build /opt/python /opt/python
COPY --from=go-judge-build /go-judge /usr/local/bin/go-judge
COPY go-judge-mount.yaml /etc/go-judge-mount.yaml
COPY worker-entrypoint.sh /usr/local/bin/worker-entrypoint
ENV PATH="/opt/python/bin:${PATH}" GO_JUDGE_URL=http://127.0.0.1:5050 FORK_PER_JOB=false
RUN chmod 755 /usr/local/bin/worker-entrypoint
ENTRYPOINT ["/usr/local/bin/worker-entrypoint"]
CMD ["/api/scripts/workers"]

# Standalone experiment: execution service contains no Rails or Ruby runtime.
FROM debian:trixie-slim AS direct
RUN apt-get update && apt-get install -y --no-install-recommends \
    libbz2-1.0 libffi8 liblzma5 libreadline8t64 libsqlite3-0 libssl3t64 \
    libncursesw6 libuuid1 zlib1g util-linux ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=sandbox-build /opt/python /opt/python
COPY --from=go-judge-build /go-judge /usr/local/bin/go-judge
COPY go-judge-mount.yaml /etc/go-judge-mount.yaml
CMD ["sh", "-c", "exec go-judge -http-addr 0.0.0.0:5050 -no-fallback -mount-conf /etc/go-judge-mount.yaml -parallelism ${GO_JUDGE_PARALLELISM:-16} -output-limit 4m -copy-out-limit 4m -src-prefix /opt/python"]
