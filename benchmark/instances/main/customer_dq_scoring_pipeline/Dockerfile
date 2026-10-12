FROM python:3.12-slim
LABEL pipeline="customer-dq-scoring-pipeline"
LABEL benchmark="prompt2serviceflow"
WORKDIR /app
COPY runtime/scripts/ /app/scripts/
RUN mkdir -p /workspace/artifacts
ENTRYPOINT ["python"]
CMD ["--help"]
