FROM php:7.4.33-apache-bullseye

ENV MW_VERSION=1.39.11 \
    APCU_VERSION=5.1.24 \
    DEBIAN_FRONTEND=noninteractive

# Packages come from a PINNED Debian snapshot, not from deb.debian.org.
#
# bullseye is oldoldstable, and its live archive is no longer internally
# consistent: on 2026-09-14 the bullseye-security index named
# libicu67 67.1-7+deb11u1 at a pool path that returns 404 on deb.debian.org,
# security.debian.org and the Fastly CDN alike, so `apt-get install libicu-dev`
# fails everywhere. That broke a cold build of this image completely - it only
# kept working locally off a cached layer.
#
# snapshot.debian.org serves the archive as it stood at one instant, index and
# pool together, so the build is both fixed and reproducible: the same
# Dockerfile produces the same packages in a year. Bump SNAPSHOT deliberately.
# Measured: the snapshot mirror installed these in ~19s, no slower in practice
# than the CDN.
ENV DEBIAN_SNAPSHOT=20260901T000000Z

# Check-Valid-Until is turned off because a snapshot's Release file is by
# definition older than "now", and apt refuses a stale index by default - every
# snapshot build would fail on the freshness check alone.
RUN set -eu; \
    printf 'deb http://snapshot.debian.org/archive/debian/%s bullseye main\n' \
        "$DEBIAN_SNAPSHOT" > /etc/apt/sources.list; \
    printf 'deb http://snapshot.debian.org/archive/debian-security/%s bullseye-security main\n' \
        "$DEBIAN_SNAPSHOT" >> /etc/apt/sources.list; \
    printf 'deb http://snapshot.debian.org/archive/debian/%s bullseye-updates main\n' \
        "$DEBIAN_SNAPSHOT" >> /etc/apt/sources.list; \
    printf 'Acquire::Check-Valid-Until "false";\n' \
        > /etc/apt/apt.conf.d/99no-check-valid-until

# Retried because snapshot.debian.org rate-limits under load. Three failures
# in a row fail the build rather than producing an image with packages
# missing, which would surface much later as a broken extension.
RUN set -eu; \
    installed=0; \
    for attempt in 1 2 3; do \
        rm -rf /var/lib/apt/lists/*; \
        if apt-get update -o Acquire::Retries=3 \
            && apt-get install -y --no-install-recommends \
                jq \
                libicu-dev \
                libpng-dev \
                libjpeg-dev \
                libfreetype6-dev \
                libzip-dev \
                libonig-dev \
                unzip \
                ca-certificates; then \
            installed=1; \
            break; \
        fi; \
        echo "apt attempt ${attempt} failed - retrying with a fresh index"; \
        sleep 10; \
    done; \
    [ "$installed" = 1 ]; \
    rm -rf /var/lib/apt/lists/*

RUN docker-php-ext-configure gd --with-freetype --with-jpeg \
    && docker-php-ext-install -j"$(nproc)" \
        calendar \
        gd \
        intl \
        mbstring \
        mysqli \
        opcache \
        zip

RUN pecl install "apcu-${APCU_VERSION}" && docker-php-ext-enable apcu

RUN a2enmod rewrite

RUN curl -fSL "https://releases.wikimedia.org/mediawiki/1.39/mediawiki-${MW_VERSION}.tar.gz" -o /tmp/mediawiki.tar.gz \
    && tar -xzf /tmp/mediawiki.tar.gz --strip-components=1 -C /var/www/html \
    && rm /tmp/mediawiki.tar.gz \
    && chown -R www-data:www-data /var/www/html

# Third-party extensions are NOT bundled with MediaWiki 1.39 core. Fetch them at
# build time from public sources pinned to exact commits in extensions.json
# (pattern borrowed from Canasta's RecommendedRevisions). They live in the image
# layer — never synced from prod, never committed to our repo. Loading the real
# LocalSettings.shared.php verbatim (the deploy-localsettings witness) requires
# every one of these present.
# Editing extensions.json (or the fetcher) busts this COPY layer and re-runs the
# download — exactly what we want when a pin changes; an unrelated rebuild reuses
# the cached layer.
COPY scripts/fetch-extensions.sh /usr/local/bin/fetch-extensions.sh
COPY extensions.json /tmp/extensions.json
RUN chmod +x /usr/local/bin/fetch-extensions.sh \
    && /usr/local/bin/fetch-extensions.sh /tmp/extensions.json /var/www/html/extensions \
    && chown -R www-data:www-data /var/www/html/extensions \
    && rm /tmp/extensions.json

WORKDIR /var/www/html

COPY entrypoint.sh /usr/local/bin/mw-entrypoint.sh
RUN chmod +x /usr/local/bin/mw-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/mw-entrypoint.sh"]
CMD ["apache2-foreground"]
