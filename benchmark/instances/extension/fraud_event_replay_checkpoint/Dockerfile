FROM python:3.12-slim
LABEL pipeline="fraud-event-replay-checkpoint"
LABEL benchmark="prompt2serviceflow"
LABEL topology="branch-gate"
WORKDIR /app
COPY runtime/scripts/ /app/scripts/
RUN mkdir -p /workspace/artifacts
ENTRYPOINT ["python"]
CMD ["--help"]
