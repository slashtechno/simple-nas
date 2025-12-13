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
    py3-pip

# Install Python packages
# pyvips: python bindings for vips
# rawpy: RAW image processing
# pillow-heif, pillow-avif-plugin: extended format support for Pillow
RUN python3 -m pip install --no-cache-dir --break-system-packages \
    pyvips \
    rawpy \
    pillow-heif \
    pillow-avif-plugin
