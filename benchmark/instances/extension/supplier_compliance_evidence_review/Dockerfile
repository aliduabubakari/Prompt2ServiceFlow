FROM python:3.12-slim

LABEL pipeline="supplier-compliance-evidence-review"
LABEL benchmark="prompt2serviceflow"
LABEL topology="fan-out-fan-in"

WORKDIR /app
COPY runtime/scripts/ /app/scripts/
RUN mkdir -p /workspace/artifacts

ENTRYPOINT ["python"]
CMD ["--help"]
