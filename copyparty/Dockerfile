FROM copyparty/ac

# Install system dependencies for thumbnail generation
# ffmpeg: video/audio thumbnails
# vips: high-performance image processing (HEIF, AVIF, JXL)
# libraw: for rawpy
# build-base, python3-dev: for compiling python packages
RUN apk add --no-cache \
    ffmpeg \
    vips-dev \
    libraw-dev \
    build-base \
    python3-dev \
    py3-cffi \
    jpeg-dev \
    zlib-dev \
    libheif-dev \
    libwebp-dev \
    py3-pip \
    git \
    pkgconf

# Install Python packages
# pyvips: python bindings for vips
# rawpy: RAW image processing (installed from git because PyPI lacks sdist)
# pillow-heif, pillow-avif-plugin: extended format support for Pillow
RUN python3 -m pip install --no-cache-dir --break-system-packages cython numpy && \
    python3 -m pip install --no-cache-dir --break-system-packages --no-build-isolation git+https://github.com/letmaik/rawpy.git && \
    python3 -m pip install --no-cache-dir --break-system-packages \
    pyvips \
    pillow-heif \
    pillow-avif-plugin

COPY copyparty.conf.template.default /etc/copyparty/copyparty.conf.template.default
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
