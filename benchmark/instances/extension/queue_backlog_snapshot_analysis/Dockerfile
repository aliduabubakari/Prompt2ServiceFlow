FROM python:3.12-slim
LABEL pipeline="queue-backlog-snapshot-analysis"
LABEL benchmark="prompt2serviceflow"
LABEL topology="windowed-batch"
WORKDIR /app
COPY runtime/scripts/ /app/scripts/
RUN mkdir -p /workspace/artifacts
ENTRYPOINT ["python"]
CMD ["--help"]
