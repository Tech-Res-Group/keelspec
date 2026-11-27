# syntax=docker/dockerfile:1
#
# A governed-agent server (`keelspec serve`) for ONE product repository.
#
# Build from the root of the repository that holds product.config.yaml, the
# committed bundle and your tool servers, not from this directory:
#
#   docker build -f <path-to-keelspec>/infra/agent-runtime/Dockerfile \
#     --build-arg KEELSPEC_SPEC="keelspec[runtime,otel]==<version>" -t payments-agents .
#
# The build runs `keelspec validate`, so an image can only be built from a bundle
# that passes the gate (I-10 holds before the container ever starts).
FROM python:3.12-slim

# Pin this to a version in production. Point it at a wheel to test unreleased code.
ARG KEELSPEC_SPEC="keelspec[runtime,otel]"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir "$KEELSPEC_SPEC" \
 && useradd --create-home --uid 10001 keelspec

WORKDIR /srv/product
COPY --chown=keelspec:keelspec . /srv/product
USER keelspec

RUN keelspec -C /srv/product validate

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).status == 200 else 1)"

# Listening on 0.0.0.0 requires KEELSPEC_SERVE_TOKEN at run time; serve refuses
# to start without it. Run records and approvals live in /srv/product/.keelspec:
# mount a volume there, or a paused run is lost when the container is replaced.
CMD ["keelspec", "-C", "/srv/product", "serve", "--host", "0.0.0.0", "--port", "8080"]
