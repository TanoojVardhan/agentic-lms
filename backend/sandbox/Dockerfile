# Code-runner sandbox image for the Assessment Agent's code questions and the
# /api/v1/code/run playground: Python 3, C (gcc) and Java 17 in one image.
#
# Build once (from the repo root):
#   docker build -t agentic-lms-runner backend/sandbox
#
# The backend starts a throwaway container from this image for every run,
# with no network, a read-only filesystem and memory/CPU/process limits
# (see backend/app/tools/code_runner.py).
#
# Everything is fetched over HTTPS: some networks block plain-HTTP package
# mirrors (port 80), which is Debian's default. The official Python image
# already ships CA certificates, so apt can use https:// right away, and
# Java is copied from the official Temurin image instead of using apt.

FROM eclipse-temurin:17-jdk AS jdk

FROM python:3.12-slim-bookworm

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=jdk /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk \
    PATH="/opt/java/openjdk/bin:${PATH}"

# Never run student code as root.
RUN useradd --create-home --uid 10001 runner
USER runner
WORKDIR /tmp
