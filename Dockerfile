FROM mcr.microsoft.com/playwright/python:v1.50.0-noble

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium \
    && apt-get update && apt-get install -y xvfb && rm -rf /var/lib/apt/lists/*

COPY . .

CMD ["xvfb-run", "--auto-servernum", "--server-args=-screen 0 1366x768x24", "python", "-u", "bot.py"]
