# Build from the deploy/helm directory so both the chart and this app are in
# the build context:
#   docker build -f clickhouse-manager/Dockerfile -t clickhouse-manager:dev .
FROM python:3.12-slim

# helm is needed to render the clickhouse-installation chart at runtime
ARG HELM_VERSION=v3.16.2
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz \
       | tar -xz -C /tmp \
    && mv /tmp/linux-amd64/helm /usr/local/bin/helm \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /tmp/linux-amd64

WORKDIR /srv
COPY clickhouse-manager/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The chart is baked in so `helm template` works without network access.
COPY clickhouse-helm-chart/ /chart/
COPY clickhouse-manager/app/ /srv/app/

ENV CHART_PATH=/chart \
    PYTHONUNBUFFERED=1 \
    PORT=8080
WORKDIR /srv/app
EXPOSE 8080
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "2", "--timeout", "120", "app:app"]
