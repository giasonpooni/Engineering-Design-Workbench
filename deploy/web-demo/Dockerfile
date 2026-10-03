# Build from the repository root with its preserved native .git history.
# This exact Python tag is configuration, not evidence that a registry build ran.
FROM python:3.12.14-slim-bookworm AS build
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install --no-install-recommends --yes git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/net-source
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
COPY scripts/prepare_web_demo.py ./scripts/prepare_web_demo.py
COPY .git/ ./.git/
RUN python scripts/prepare_web_demo.py --environment /opt/net-venv --providers /opt/net-providers

FROM python:3.12.14-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/opt/net-venv/bin:$PATH" \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
# Git verifies exact provider commit/tree/bytes at runtime; no remote is needed.
RUN apt-get update && apt-get install --no-install-recommends --yes git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 net-demo \
    && useradd --uid 10001 --gid 10001 --no-create-home \
       --home-dir /nonexistent --shell /usr/sbin/nologin net-demo
COPY --from=build /opt/net-venv /opt/net-venv
COPY --from=build /opt/net-providers /opt/net-providers
RUN chown -R 10001:10001 /opt/net-providers
USER 10001:10001
WORKDIR /tmp
EXPOSE 4173
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD ["python", "-I", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:4173/api/health', timeout=3).read()"]
CMD ["python", "-I", "-m", "ciw.demo_server", "--gsie-repo", "/opt/net-providers/gsie", "--jspt-repo", "/opt/net-providers/jspt", "--host", "0.0.0.0", "--port", "4173"]
