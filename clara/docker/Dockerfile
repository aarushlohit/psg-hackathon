FROM python:3.11-slim AS base

WORKDIR /app

# Install dependencies
COPY clara/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY clara/ clara/
COPY pyproject.toml .

# Create non-root user
RUN useradd --create-home clara && \
    mkdir -p /home/clara/.clara/uploads /home/clara/.clara/logs && \
    chown -R clara:clara /home/clara /app
USER clara

ENV CLARA_HOST=0.0.0.0
ENV CLARA_PORT=9100
EXPOSE 9100

CMD ["python", "-m", "clara.server.main", "--host", "0.0.0.0", "--port", "9100"]
