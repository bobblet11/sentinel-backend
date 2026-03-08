# Step 1: Start from our base image
FROM sentinel/python-light-common:3.11

WORKDIR /app

ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    wget \
    gnupg \
    ca-certificates \
    unzip \
    xvfb \
    xfonts-base \
    && if [ "$TARGETARCH" = "arm64" ]; then \
        # ARM: Install Chromium + chromedriver from apt
        apt-get install -y chromium chromium-driver; \
    else \
        # x86_64: Install Google Chrome
        apt-get install -y \
            libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
            libxkbcommon0 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
            libxrandr2 libgbm1 libasound2 libpangocairo-1.0-0 libgtk-3-0 \
            xvfb xserver-xephyr tigervnc-standalone-server xfonts-base \
        && wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
        && apt-get install -y ./google-chrome-stable_current_amd64.deb \
        && rm google-chrome-stable_current_amd64.deb; \
    fi \
    && apt-get clean && rm -rf /var/lib/apt/lists/*


COPY microservices/web_scraper/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY microservices/web_scraper /app/microservices/web_scraper

CMD ["python", "-m", "microservices.web_scraper.main"]
