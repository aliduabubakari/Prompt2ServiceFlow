FROM python:3.12-slim

LABEL pipeline="fraud-detection-triage"
LABEL benchmark="prompt2serviceflow"
LABEL topology="branch-merge"

WORKDIR /app
COPY runtime/scripts/ /app/scripts/
RUN mkdir -p /workspace/artifacts

ENTRYPOINT ["python"]
CMD ["--help"]
