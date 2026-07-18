FROM python:3.11-slim

WORKDIR /opt/stn-cli

# Copy only the package sources (see .dockerignore) and install the CLI, which
# puts the `stn` entry point on PATH via [project.scripts].
COPY pyproject.toml ./
COPY stn_cli ./stn_cli
RUN pip install --no-cache-dir .

# Default to the ai-service container on the compose network; override with
# STN_API / STN_TOKEN at run time.
ENV STN_API=http://ai-service:8000 \
    PYTHONUNBUFFERED=1

ENTRYPOINT ["stn"]
CMD ["--help"]
