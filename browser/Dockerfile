FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Display stack + noVNC + fonts + tools
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg wget \
        xvfb x11vnc novnc websockify openbox \
        fonts-liberation fonts-noto-color-emoji \
        procps iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Google Chrome (stable)
RUN curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
        | gpg --dearmor -o /usr/share/keyrings/google.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
        > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Node.js 22 (Stagehand runtime)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Stagehand SDK + OpenAI (LiteLLM BYO-LLM) + zod
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund --legacy-peer-deps

COPY stagehand-server.mjs ./

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 6080 8931

ENTRYPOINT ["/entrypoint.sh"]
