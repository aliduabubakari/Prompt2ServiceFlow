FROM python:3.12-slim

LABEL pipeline="environmental-sensor-anomaly-batch"
LABEL benchmark="prompt2serviceflow"
LABEL topology="windowed-batch"

WORKDIR /app
COPY runtime/scripts/ /app/scripts/
RUN mkdir -p /workspace/artifacts

ENTRYPOINT ["python"]
CMD ["--help"]
