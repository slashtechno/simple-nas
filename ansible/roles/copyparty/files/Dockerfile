FROM copyparty/ac

# Install system dependencies for thumbnail generation
# ffmpeg: video/audio thumbnails
# vips: high-performance image processing (HEIF, AVIF, JXL)
# libraw: for rawpy (RAW camera file decoding)
# build-base, python3-dev, cmake, git: for compiling rawpy from source
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
    cmake

# Install Python packages
# rawpy: RAW image processing (compiled from git; MAKEFLAGS parallelizes)
# pyvips: python bindings for vips
# pillow-heif, pillow-avif-plugin: extended format support for Pillow
RUN MAKEFLAGS="-j$(nproc)" python3 -m pip install --no-cache-dir --break-system-packages cython numpy && \
    MAKEFLAGS="-j$(nproc)" python3 -m pip install --no-cache-dir --break-system-packages --no-build-isolation git+https://github.com/letmaik/rawpy.git && \
    python3 -m pip install --no-cache-dir --break-system-packages \
    pyvips \
    pillow-heif \
    pillow-avif-plugin

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
