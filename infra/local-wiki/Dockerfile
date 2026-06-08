FROM php:7.4.33-apache-bullseye

ENV MW_VERSION=1.39.11 \
    APCU_VERSION=5.1.24 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        libicu-dev \
        libpng-dev \
        libjpeg-dev \
        libfreetype6-dev \
        libzip-dev \
        libonig-dev \
        unzip \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

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
# build time from public sources pinned to exact commits in extensions.lock
# (pattern borrowed from Canasta's RecommendedRevisions). They live in the image
# layer — never synced from prod, never committed to our repo. Loading the real
# LocalSettings.shared.php verbatim (the deploy-localsettings witness) requires
# every one of these present.
# Editing extensions.lock (or the fetcher) busts this COPY layer and re-runs the
# clone — exactly what we want when a pin changes; an unrelated rebuild reuses
# the cached layer.
COPY scripts/fetch-extensions.sh /usr/local/bin/fetch-extensions.sh
COPY extensions.lock /tmp/extensions.lock
RUN chmod +x /usr/local/bin/fetch-extensions.sh \
    && /usr/local/bin/fetch-extensions.sh /tmp/extensions.lock /var/www/html/extensions \
    && chown -R www-data:www-data /var/www/html/extensions \
    && rm /tmp/extensions.lock

WORKDIR /var/www/html

COPY entrypoint.sh /usr/local/bin/mw-entrypoint.sh
RUN chmod +x /usr/local/bin/mw-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/mw-entrypoint.sh"]
CMD ["apache2-foreground"]
