FROM python:3.12-slim

LABEL pipeline="clickstream-session-window-batch"
LABEL benchmark="prompt2serviceflow"
LABEL topology="linear-windowed"

WORKDIR /app

# Copy runtime scripts
COPY runtime/scripts/ /app/scripts/

# Scripts use Python stdlib only — no additional dependencies
# If dependencies are ever needed, add:
# COPY pyproject.toml uv.lock /app/
# RUN pip install uv && uv sync --frozen

# Workspace for artifact sharing between tasks
RUN mkdir -p /workspace/artifacts

ENTRYPOINT ["python"]
CMD ["--help"]
