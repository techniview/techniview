FROM mrkushalsm/judge0@sha256:d60605ad448453ac3754629bc7121d379cf691e0c091aabbc03ff2886b2626b2 AS judge0_source

FROM judge0/compilers:1.4.0-slim@sha256:ed9bbf7b440de3c44cc043b7143f1fabb09726f37f185af5a828cc34afdaa653

ARG PYTHON_VERSION=3.14.8
ARG PYTHON_SHA256=c2215904f02b175596dc49351585104f4bc20341e1c47378b26a2c274360ce73

ENV PATH="/usr/local/ruby-2.7.0/bin:/opt/.gem/bin:/usr/local/python-${PYTHON_VERSION}/bin:${PATH}" \
    GEM_HOME=/opt/.gem/ \
    JUDGE0_HOMEPAGE=https://judge0.com \
    JUDGE0_SOURCE_CODE=https://github.com/judge0/judge0 \
    JUDGE0_VERSION=1.13.1

RUN set -eux; \
    sed -i \
      -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' \
      -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' \
      /etc/apt/sources.list; \
    printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99no-check-valid-until; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      cron \
      curl \
      libbz2-dev \
      libffi-dev \
      liblzma-dev \
      libpq-dev \
      libreadline-dev \
      libsqlite3-dev \
      libssl-dev \
      patch \
      sudo \
      uuid-dev \
      zlib1g-dev; \
    rm -rf /var/lib/apt/lists/*

COPY --from=judge0_source /usr/local/ruby-2.7.0 /usr/local/ruby-2.7.0
COPY --from=judge0_source /opt/.gem /opt/.gem
COPY --from=judge0_source /api /api
COPY --from=judge0_source /usr/local/bin/isolate /usr/local/bin/isolate
COPY --from=judge0_source /usr/local/bin/isolate-check-environment /usr/local/bin/isolate-check-environment
COPY --from=judge0_source /usr/local/sbin/isolate-cg-keeper /usr/local/sbin/isolate-cg-keeper
COPY --from=judge0_source /usr/local/etc/isolate /usr/local/etc/isolate

COPY languages/active.rb /api/db/languages/active.rb
COPY languages/archived.rb /api/db/languages/archived.rb
COPY patches/single-language-api.patch /tmp/single-language-api.patch

RUN set -eux; \
    cd /api; \
    patch -p1 < /tmp/single-language-api.patch; \
    rm /tmp/single-language-api.patch; \
    cd /; \
    curl -fSsL "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tar.xz" -o /tmp/python.tar.xz; \
    echo "${PYTHON_SHA256}  /tmp/python.tar.xz" | sha256sum -c -; \
    mkdir /tmp/python; \
    tar -xf /tmp/python.tar.xz -C /tmp/python --strip-components=1; \
    cd /tmp/python; \
    ./configure --prefix="/usr/local/python-${PYTHON_VERSION}" --with-ensurepip=install; \
    make -j"$(nproc)"; \
    make install; \
    cd /; \
    rm -rf /tmp/python /tmp/python.tar.xz; \
    chmod 4755 /usr/local/bin/isolate /usr/local/sbin/isolate-cg-keeper; \
    echo 'gem: --no-document' > /root/.gemrc; \
    gem install bundler:2.1.4; \
    cd /api; \
    RAILS_ENV=production bundle; \
    cp cron/* /etc/cron.d/; \
    cat /etc/cron.d/* | crontab -; \
    useradd -u 1000 -m -r judge0; \
    echo 'judge0 ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers; \
    chown judge0: /api/tmp/; \
    python3.14 --version

EXPOSE 2358
WORKDIR /api
ENTRYPOINT ["/api/docker-entrypoint.sh"]
CMD ["/api/scripts/server"]
USER judge0
