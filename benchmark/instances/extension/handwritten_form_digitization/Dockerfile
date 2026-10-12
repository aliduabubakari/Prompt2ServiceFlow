FROM python:3.12-slim
LABEL pipeline="handwritten-form-digitization"
LABEL benchmark="prompt2serviceflow"
LABEL topology="staged-etl"
WORKDIR /app
COPY runtime/scripts/ /app/scripts/
RUN mkdir -p /workspace/artifacts
ENTRYPOINT ["python"]
CMD ["--help"]
