FROM python:3.12-slim

LABEL pipeline="scanned-claim-packet-extraction"
LABEL benchmark="prompt2serviceflow"
LABEL topology="fan-out"

WORKDIR /app
COPY runtime/scripts/ /app/scripts/
RUN mkdir -p /workspace/artifacts

ENTRYPOINT ["python"]
CMD ["--help"]
