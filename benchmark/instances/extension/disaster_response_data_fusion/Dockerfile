FROM python:3.12-slim
LABEL pipeline="disaster-response-data-fusion"
LABEL benchmark="prompt2serviceflow"
LABEL topology="fan-out-fan-in"
WORKDIR /app
COPY runtime/scripts/ /app/scripts/
RUN mkdir -p /workspace/artifacts
ENTRYPOINT ["python"]
CMD ["--help"]
