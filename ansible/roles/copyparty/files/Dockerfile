# iv = ffmpeg + vips + libraw (RAW thumbnails, including NEF). The tag is copyparty_base_image in group_vars/all/versions.yml.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

# ffmpeg: video and audio thumbnails. vips: image processing (HEIF, AVIF, JXL). libraw: RAW decoding.
# build-base, python3-dev: for Python packages without prebuilt wheels.
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
    # git and cmake are needed only to compile rawpy; see the rawpy block below
    # git \
    # cmake

# The rawpy install below is commented out; keep it, and ask the owner before deleting it.
# The official image makes RAW thumbnails (NEF etc.) with libraw directly: slower than rawpy but good quality.
# Sony .ARW thumbnails need rawpy. To switch rawpy on (also if RAW thumbnails are too slow): uncomment the
# next two lines, and the git and cmake packages above (plus the "\" after py3-pip), and rebuild (the
# rawpy compile takes many minutes on a Pi).
# RUN MAKEFLAGS="-j$(nproc)" python3 -m pip install --no-cache-dir --break-system-packages setuptools cython numpy && \
#     MAKEFLAGS="-j$(nproc)" python3 -m pip install --no-cache-dir --break-system-packages --no-build-isolation git+https://github.com/letmaik/rawpy.git

# Python packages the official image leaves out because HEIF/HEIC cannot ship in it:
# pyvips (bindings for vips), pillow-heif and pillow-avif-plugin (extra Pillow formats).
RUN python3 -m pip install --no-cache-dir --break-system-packages \
    pyvips \
    pillow-heif \
    pillow-avif-plugin

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
