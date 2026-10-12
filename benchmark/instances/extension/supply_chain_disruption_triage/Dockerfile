FROM python:3.12-slim
LABEL pipeline="supply-chain-disruption-triage"
LABEL benchmark="servicecomposebench-etl"
WORKDIR /app
COPY runtime/scripts/ /app/scripts/
RUN mkdir -p /workspace/artifacts
ENTRYPOINT ["python"]
CMD ["--help"]
