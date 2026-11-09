// M5 agent driver: runs the Pi agent inside the isolated container.
//
// Environment:
//   P2SF_MODEL_NAME   - model id exposed by the proxy provider (required)
//   P2SF_PROXY_BASE   - proxy base URL, e.g. http://p2sf-proxy:8787/v1
//   P2SF_PROXY_KEY    - dummy key (the proxy injects the real key upstream)
//   P2SF_TRANSCRIPT   - transcript JSONL path (default /workspace/.agent/transcript.jsonl)
//
// The driver registers a single OpenAI-compatible provider pointing at the
// proxy, creates a session rooted at /workspace with a fixed tool set,
// records a JSONL transcript of tool calls and messages, sends METHOD.md as
// the task prompt, and exits when the agent finishes.

import fs from "node:fs";
import path from "node:path";
import {
  createAgentSession,
  DefaultResourceLoader,
  ModelRuntime,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";

const MODEL_NAME = process.env.P2SF_MODEL_NAME;
const CONTEXT_WINDOW = Number.parseInt(process.env.P2SF_CONTEXT_WINDOW || "100000", 10);
const MAX_TOKENS = Number.parseInt(process.env.P2SF_MAX_TOKENS || "16384", 10);
const MAX_IDLE_CONTINUATIONS = Number.parseInt(
  process.env.P2SF_MAX_IDLE_CONTINUATIONS || "6",
  10,
);
const VALIDATOR_BUDGET = Number.parseInt(process.env.P2SF_VALIDATOR_BUDGET || "4", 10);
const MAX_AGENT_STEPS = Number.parseInt(process.env.P2SF_MAX_AGENT_STEPS || "12", 10);
const PROXY_BASE = process.env.P2SF_PROXY_BASE || "http://p2sf-proxy:8787/v1";
const TRANSCRIPT_PATH =
  process.env.P2SF_TRANSCRIPT || "/workspace/.agent/transcript.jsonl";
const WORKSPACE = "/workspace";
const AGENT_DIR = "/opt/p2sf/agent";

if (!MODEL_NAME) {
  console.error("P2SF_MODEL_NAME is not set");
  process.exit(2);
}
if (!fs.existsSync(path.join(WORKSPACE, "METHOD.md"))) {
  console.error("METHOD.md missing in /workspace");
  process.exit(2);
}

fs.mkdirSync(path.dirname(TRANSCRIPT_PATH), { recursive: true });
const transcript = fs.createWriteStream(TRANSCRIPT_PATH, { flags: "a" });
function record(event) {
  transcript.write(JSON.stringify({ ts: new Date().toISOString(), ...event }) + "\n");
}

// Register the proxy as a custom provider via models.json (the resolvable
// path for ModelRuntime.getModel; "$P2SF_PROXY_KEY" is resolved by pi from
// the environment at request time).
fs.mkdirSync(AGENT_DIR, { recursive: true });
fs.writeFileSync(
  path.join(AGENT_DIR, "models.json"),
  JSON.stringify(
    {
      providers: {
        "p2sf-proxy": {
          baseUrl: PROXY_BASE,
          apiKey: "$P2SF_PROXY_KEY",
          api: "openai-completions",
          models: [
            {
              id: MODEL_NAME,
              name: MODEL_NAME,
              reasoning: false,
              input: ["text"],
              cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
              contextWindow: CONTEXT_WINDOW,
              maxTokens: MAX_TOKENS,
            },
          ],
        },
      },
    },
    null,
    2,
  ),
);

const modelRuntime = await ModelRuntime.create({
  authPath: path.join(AGENT_DIR, "auth.json"),
  modelsPath: path.join(AGENT_DIR, "models.json"),
});
const loader = new DefaultResourceLoader({
  cwd: WORKSPACE,
  agentDir: AGENT_DIR,
});
await loader.reload();

const model = modelRuntime.getModel("p2sf-proxy", MODEL_NAME);
if (!model) {
  console.error(`model ${MODEL_NAME} not resolvable via proxy provider`);
  process.exit(2);
}

const { session } = await createAgentSession({
  cwd: WORKSPACE,
  agentDir: AGENT_DIR,
  resourceLoader: loader,
  modelRuntime,
  model,
  tools: ["read", "bash", "edit", "write", "grep", "find", "ls"],
  sessionManager: SessionManager.inMemory(),
  settingsManager: SettingsManager.inMemory({ compaction: { enabled: true } }),
});

let lastAssistantStopReason;
let lastAssistantError;
let agentSteps = 0;
let agentStepBudgetExhausted = false;
let protocolNudgeIssued = false;

session.subscribe(async (event) => {
  switch (event.type) {
    case "tool_execution_start":
      record({
        type: "tool_execution_start",
        tool: event.toolName,
        args: safe(event.args ?? event.toolCall?.arguments),
      });
      break;
    case "tool_execution_end":
      record({ type: "tool_execution_end", tool: event.toolName, is_error: !!event.isError });
      break;
    case "message_end": {
      const message = event.message;
      if (message?.role === "assistant") {
        lastAssistantStopReason = message.stopReason;
        lastAssistantError = message.errorMessage;
        record({
          type: "assistant_message",
          stop_reason: message.stopReason,
          error: message.errorMessage,
          usage: message.usage
            ? {
                input: message.usage.input,
                output: message.usage.output,
                total: message.usage.totalTokens,
              }
            : undefined,
          text: textOf(message),
        });
      }
      break;
    }
    case "agent_end":
      record({ type: "agent_end" });
      break;
    case "turn_end":
      if (lastAssistantStopReason === "aborted") break;
      agentSteps += 1;
      record({ type: "agent_step", step: agentSteps, budget: MAX_AGENT_STEPS });
      {
        const state = protocolState();
        const protocolComplete = state.submissionReady &&
          (state.lastValidatorStatus === 0 || state.validatorCalls >= VALIDATOR_BUDGET);
        if (agentSteps >= MAX_AGENT_STEPS && !protocolComplete) {
          agentStepBudgetExhausted = true;
          await session.agent.abort();
        } else if (
          state.irAuthored &&
          state.validatorCalls === 0 &&
          !protocolNudgeIssued
        ) {
          // Once the source IR exists, stop open-ended inspection and return
          // control to the protocol loop so compile + validation happen while
          // agent-step budget remains.
          protocolNudgeIssued = true;
          await session.agent.abort();
        }
      }
      break;
    default:
      break;
  }
});

function textOf(message) {
  try {
    return (message.content || [])
      .filter((block) => block.type === "text")
      .map((block) => block.text)
      .join("\n")
      .slice(0, 4000);
  } catch {
    return undefined;
  }
}

function safe(value) {
  try {
    return JSON.parse(JSON.stringify(value ?? null));
  } catch {
    return null;
  }
}

const instructions = fs.readFileSync(path.join(WORKSPACE, "METHOD.md"), "utf-8");
record({ type: "run_start", model: MODEL_NAME, proxy: PROXY_BASE });

function protocolState() {
  const scriptsDir = path.join(WORKSPACE, "submission", "runtime", "scripts");
  const irAuthored = fs.existsSync(
    path.join(WORKSPACE, "submission", "serviceflow.yaml"),
  );
  const submissionReady =
    irAuthored &&
    fs.existsSync(path.join(WORKSPACE, "submission", "runtime", "manifest.yaml")) &&
    fs.existsSync(scriptsDir) &&
    fs.readdirSync(scriptsDir).some((name) => name.endsWith(".py"));
  const validatorCallsPath = path.join(WORKSPACE, "bin", ".validator_calls");
  const validatorCalls = fs.existsSync(validatorCallsPath)
    ? Number.parseInt(fs.readFileSync(validatorCallsPath, "utf-8").trim() || "0", 10)
    : 0;
  const validatorStatusPath = path.join(WORKSPACE, "bin", ".last_validator_status");
  const rawStatus = fs.existsSync(validatorStatusPath)
    ? fs.readFileSync(validatorStatusPath, "utf-8").trim()
    : "";
  const lastValidatorStatus = rawStatus === "" ? null : Number.parseInt(rawStatus, 10);
  return { irAuthored, submissionReady, validatorCalls, lastValidatorStatus };
}

function tokenBudgetExhausted() {
  const error = String(lastAssistantError || "").toLowerCase();
  return error.includes("token") &&
    (error.includes("budget exhausted") || error.includes("cap"));
}

try {
  await session.prompt(instructions);
  await session.agent.waitForIdle();
  for (let continuation = 1; continuation <= MAX_IDLE_CONTINUATIONS; continuation += 1) {
    if (tokenBudgetExhausted() || agentStepBudgetExhausted) break;
    const { submissionReady, validatorCalls, lastValidatorStatus } = protocolState();
    const validatorPassed = validatorCalls > 0 && lastValidatorStatus === 0;
    const validatorBudgetExhausted = validatorCalls >= VALIDATOR_BUDGET;
    if (submissionReady && (validatorPassed || validatorBudgetExhausted)) break;
    record({
      type: "controller_continuation",
      continuation,
      submission_ready: submissionReady,
      validator_calls: validatorCalls,
      last_validator_status: lastValidatorStatus,
      last_assistant_stop_reason: lastAssistantStopReason,
    });
    await session.prompt(
      "The experiment protocol is not complete: a valid submission has not passed the public " +
        "validator and validator budget remains. Continue working now; do not apologize or " +
        "summarize. Inspect the latest validator diagnostics, repair every reported issue in " +
        "submission/serviceflow.yaml, run bin/compile --workspace ., then invoke " +
        "bin/validate_submission --workspace . again. Do not edit derived runtime or Argo files. " +
        "Do not inspect tool implementations. Quote YAML strings that contain colons and use " +
        "exact schema types and enum values.",
    );
    await session.agent.waitForIdle();
  }
  const finalState = protocolState();
  let runStatus;
  if (tokenBudgetExhausted()) {
    runStatus = "token_budget_exhausted";
  } else if (agentStepBudgetExhausted) {
    runStatus = "agent_step_budget_exhausted";
  } else if (finalState.submissionReady && finalState.lastValidatorStatus === 0) {
    runStatus = "completed";
  } else if (
    finalState.submissionReady &&
    finalState.validatorCalls >= VALIDATOR_BUDGET
  ) {
    runStatus = "validator_budget_exhausted";
  } else if (lastAssistantStopReason === "error") {
    runStatus = "model_error";
  } else {
    runStatus = "incomplete_protocol";
  }
  record({
    type: "run_end",
    status: runStatus,
    submission_ready: finalState.submissionReady,
    validator_calls: finalState.validatorCalls,
    last_validator_status: finalState.lastValidatorStatus,
    last_assistant_stop_reason: lastAssistantStopReason,
    last_assistant_error: lastAssistantError,
    agent_steps: agentSteps,
    agent_step_budget: MAX_AGENT_STEPS,
  });
  await new Promise((resolve, reject) => {
    transcript.once("error", reject);
    transcript.end(resolve);
  });
  process.exitCode =
    runStatus === "completed" ||
    runStatus === "validator_budget_exhausted" ||
    runStatus === "token_budget_exhausted" ||
    runStatus === "agent_step_budget_exhausted"
      ? 0
      : 4;
} catch (error) {
  record({ type: "run_end", status: "error", message: String(error) });
  await new Promise((resolve) => transcript.end(resolve));
  process.exitCode = 1;
}
