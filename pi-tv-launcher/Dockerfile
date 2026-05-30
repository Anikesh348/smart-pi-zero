FROM python:3.11-slim

ARG INSTALL_BROWSER=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        alsa-utils \
        ca-certificates \
        curl \
        procps \
        xdotool \
    && if [ "$INSTALL_BROWSER" = "1" ]; then \
        apt-get install -y --no-install-recommends surf; \
    fi \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python", "app.py"]
