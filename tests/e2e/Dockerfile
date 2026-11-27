# Clean Linux install test. Nothing from the host is mounted: the repository is copied in, the fake `claude` stands in
# for Claude Code, and the run is unprivileged with HOME inside the container.
#   docker build -f tests/e2e/Dockerfile -t control-tower-e2e . && docker run --rm --network none control-tower-e2e
FROM python:3.9-slim
RUN apt-get update && apt-get install -y --no-install-recommends git cron bubblewrap socat && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home tester
COPY --chown=tester:tester . /repo
USER tester
ENV CT_E2E_CONTAINER=1
WORKDIR /repo
CMD ["sh", "-c", "python3 -W ignore -m unittest discover -s tests -p 'test_*.py' && python3 tests/e2e/run_e2e.py"]
