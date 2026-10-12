FROM python:3.12-slim

LABEL pipeline="medical-image-metadata-quality-check"
LABEL benchmark="prompt2serviceflow"
LABEL topology="linear"

WORKDIR /app
COPY runtime/scripts/ /app/scripts/
RUN mkdir -p /workspace/artifacts

ENTRYPOINT ["python"]
CMD ["--help"]
