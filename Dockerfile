FROM python:3.11-slim

# System dependencies: ffmpeg (MoviePy), ImageMagick (Subtitles)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    imagemagick \
    libmagickwand-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Fix ImageMagick security policy (blocks PDF/video operations by default)
RUN sed -i 's/rights="none" pattern="PDF"/rights="read|write" pattern="PDF"/' /etc/ImageMagick-6/policy.xml || true && \
    sed -i 's/<policy domain="path" rights="none" pattern="@\*"\/>/<policy domain="path" rights="read|write" pattern="@*"\/>/' /etc/ImageMagick-6/policy.xml || true

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Media dir for generated videos (ephemeral on Railway — videos are uploaded to TikTok immediately)
RUN mkdir -p /app/media

ENV MEDIA_DIR=/app/media

EXPOSE 8000

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
