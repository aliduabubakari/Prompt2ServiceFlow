FROM python:3.12-slim
LABEL pipeline="crm-sales-enrichment-fusion"
LABEL benchmark="prompt2serviceflow"
LABEL topology="fan-in"
WORKDIR /app
COPY runtime/scripts/ /app/scripts/
RUN mkdir -p /workspace/artifacts
ENTRYPOINT ["python"]
CMD ["--help"]
