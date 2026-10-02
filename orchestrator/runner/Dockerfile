FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        git python3 python3-pip python3-venv curl ca-certificates nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Non-root runner user (uid/gid 1001; ubuntu base image reserves 1000).
RUN useradd -u 1001 -m runner

# aider (coding agent)
RUN pip3 install --no-cache-dir --break-system-packages aider-chat

# opencode (coding agent CLI)
RUN curl -fsSL https://opencode.ai/install | bash

USER runner
WORKDIR /workspace

ENTRYPOINT ["/bin/bash", "-c"]
