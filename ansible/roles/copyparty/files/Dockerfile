# iv = ffmpeg + vips + libraw (RAW thumbnails, including NEF). The tag is copyparty_base_image in group_vars/nas/versions.yml.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# Install system dependencies for thumbnail generation
# ffmpeg: video/audio thumbnails
# vips: high-performance image processing (HEIF, AVIF, JXL)
# libraw: RAW camera file decoding
# build-base, python3-dev: for compiling Python packages without prebuilt wheels
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
    # git and cmake were only for compiling rawpy; see the rawpy block below
    # git \
    # cmake

# rawpy is DISABLED, not deleted. Do not remove this block without asking the owner.
# Since copyparty 1.20.16 the official images make RAW thumbnails (NEF etc.) with libraw directly:
# slower than rawpy but good quality. Re-enable if RAW thumbnails are too slow, or for Sony .ARW,
# which needed rawpy as of 1.20.7. To re-enable: uncomment the next two lines, and the git and
# cmake packages above (plus the "\" after py3-pip), and rebuild (the rawpy compile takes many minutes on a Pi).
# RUN MAKEFLAGS="-j$(nproc)" python3 -m pip install --no-cache-dir --break-system-packages setuptools cython numpy && \
#     MAKEFLAGS="-j$(nproc)" python3 -m pip install --no-cache-dir --break-system-packages --no-build-isolation git+https://github.com/letmaik/rawpy.git

# Python packages the official image leaves out (HEIF/HEIC cannot ship in the official images):
# pyvips: python bindings for vips
# pillow-heif, pillow-avif-plugin: extended format support for Pillow
RUN python3 -m pip install --no-cache-dir --break-system-packages \
    pyvips \
    pillow-heif \
    pillow-avif-plugin

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
