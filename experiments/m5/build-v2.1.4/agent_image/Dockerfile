FROM python:3.12-slim
COPY --from=node:22-bookworm-slim /usr/local /usr/local
WORKDIR /opt/p2sf
# Local install: ESM imports from agent_driver.mjs resolve /opt/p2sf/node_modules
# (a global npm install would not be resolvable from an arbitrary script).
RUN npm init -y >/dev/null && npm install --ignore-scripts @earendil-works/pi-coding-agent@0.82.0
WORKDIR /opt/p2sf/pkg
COPY pkg/pyproject.toml ./pyproject.toml
COPY pkg/src ./src
RUN pip install --no-cache-dir .
# The Argo compiler resolves its repository-level JSON schemas relative to
# the installed package root. Ship the public schema bundle at that exact
# runtime location so compile_submission is portable inside the image.
COPY pkg/schemas /usr/local/lib/python3.12/schemas
COPY agent_driver.mjs /opt/p2sf/agent_driver.mjs
RUN mkdir -p /opt/p2sf/agent /workspace
WORKDIR /workspace
ENTRYPOINT ["node", "/opt/p2sf/agent_driver.mjs"]
