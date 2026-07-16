#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { readFile, stat } from "node:fs/promises";
import { isIP } from "node:net";
import { pathToFileURL } from "node:url";

export const ENVIRONMENT = "external-canaries";

export const REQUIRED_SECRET_NAMES = [
  "GRAPHVIEW_CANARY_GITHUB_TOKEN",
  "GRAPHVIEW_CANARY_GOOGLE_CLIENT_ID",
  "GRAPHVIEW_CANARY_GOOGLE_CLIENT_SECRET",
  "GRAPHVIEW_CANARY_GOOGLE_REFRESH_TOKEN",
  "GRAPHVIEW_CANARY_NOTION_TOKEN",
  "GRAPHVIEW_CANARY_OPENAI_API_KEY",
  "GRAPHVIEW_CANARY_WEBHOOK_SECRET"
];

export const OPTIONAL_SECRET_NAMES = [
  "GRAPHVIEW_CANARY_SMTP_USERNAME",
  "GRAPHVIEW_CANARY_SMTP_PASSWORD"
];

export const REQUIRED_VARIABLE_NAMES = [
  "GRAPHVIEW_CANARY_GITHUB_REPOSITORY",
  "GRAPHVIEW_CANARY_GOOGLE_FOLDER_ID",
  "GRAPHVIEW_CANARY_NOTION_TARGET_ID",
  "GRAPHVIEW_CANARY_NOTION_TARGET_TYPE",
  "GRAPHVIEW_CANARY_OPENAI_MODEL",
  "GRAPHVIEW_CANARY_SMTP_RECIPIENT",
  "GRAPHVIEW_CANARY_WEBHOOK_URL",
  "GRAPHVIEW_CANARY_SMTP_HOST",
  "GRAPHVIEW_CANARY_SMTP_PORT",
  "GRAPHVIEW_CANARY_SMTP_STARTTLS",
  "GRAPHVIEW_CANARY_SMTP_FROM_ADDRESS"
];

const ALL_SECRET_NAMES = [...REQUIRED_SECRET_NAMES, ...OPTIONAL_SECRET_NAMES];
const PLACEHOLDER = /^(?:change[-_ ]?me|replace|todo|example|<)/i;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const HOSTNAME = /^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/i;

function isConfigured(value) {
  return typeof value === "string" && value.trim().length > 0 && !PLACEHOLDER.test(value.trim());
}

function isPublicHttps(value) {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    if (url.protocol !== "https:" || url.username || url.password || url.hash) return false;
    if (isIP(host.replace(/^\[|\]$/g, "")) !== 0) return false;
    if ([".invalid", ".example", ".test", ".localhost", ".local"].some((suffix) => host.endsWith(suffix))) return false;
    if (host === "localhost") return false;
    return Boolean(host);
  } catch {
    return false;
  }
}

export function parseConfigurationDocument(text) {
  const document = JSON.parse(text);
  if (!document || typeof document !== "object" || Array.isArray(document)) {
    throw new Error("Canary configuration must be a JSON object.");
  }
  for (const section of ["secrets", "variables"]) {
    if (!document[section] || typeof document[section] !== "object" || Array.isArray(document[section])) {
      throw new Error(`Canary configuration requires a ${section} object.`);
    }
  }
  const unknownSections = Object.keys(document).filter((name) => !["secrets", "variables"].includes(name));
  if (unknownSections.length > 0) {
    throw new Error(`Unknown canary configuration section(s): ${unknownSections.sort().join(", ")}`);
  }
  const knownSecrets = new Set(ALL_SECRET_NAMES);
  const knownVariables = new Set(REQUIRED_VARIABLE_NAMES);
  const unknown = [
    ...Object.keys(document.secrets).filter((name) => !knownSecrets.has(name)),
    ...Object.keys(document.variables).filter((name) => !knownVariables.has(name))
  ];
  if (unknown.length > 0) throw new Error(`Unknown canary configuration name(s): ${unknown.sort().join(", ")}`);
  return { secrets: document.secrets, variables: document.variables };
}

export function validateCanaryConfiguration({ secrets = {}, variables = {} }) {
  const errors = [];
  for (const name of REQUIRED_SECRET_NAMES) {
    if (!isConfigured(secrets[name])) errors.push(`${name} is required`);
  }
  for (const name of REQUIRED_VARIABLE_NAMES) {
    if (!isConfigured(variables[name])) errors.push(`${name} is required`);
  }

  const smtpUsername = isConfigured(secrets.GRAPHVIEW_CANARY_SMTP_USERNAME);
  const smtpPassword = isConfigured(secrets.GRAPHVIEW_CANARY_SMTP_PASSWORD);
  if (smtpUsername !== smtpPassword) {
    errors.push("GRAPHVIEW_CANARY_SMTP_USERNAME and GRAPHVIEW_CANARY_SMTP_PASSWORD must be configured together");
  }
  for (const name of ALL_SECRET_NAMES) {
    if (isConfigured(secrets[name]) && /[\r\n]/.test(secrets[name])) errors.push(`${name} must be a single-line value`);
  }
  if (isConfigured(secrets.GRAPHVIEW_CANARY_WEBHOOK_SECRET)
      && secrets.GRAPHVIEW_CANARY_WEBHOOK_SECRET.trim().length < 32) {
    errors.push("GRAPHVIEW_CANARY_WEBHOOK_SECRET must contain at least 32 characters");
  }
  if (isConfigured(variables.GRAPHVIEW_CANARY_GITHUB_REPOSITORY)
      && !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(variables.GRAPHVIEW_CANARY_GITHUB_REPOSITORY)) {
    errors.push("GRAPHVIEW_CANARY_GITHUB_REPOSITORY must use owner/repository format");
  }
  if (isConfigured(variables.GRAPHVIEW_CANARY_GOOGLE_FOLDER_ID)
      && !/^[A-Za-z0-9_-]+$/.test(variables.GRAPHVIEW_CANARY_GOOGLE_FOLDER_ID)) {
    errors.push("GRAPHVIEW_CANARY_GOOGLE_FOLDER_ID has an invalid format");
  }
  if (isConfigured(variables.GRAPHVIEW_CANARY_NOTION_TARGET_ID)
      && !/^[A-Fa-f0-9-]{32,36}$/.test(variables.GRAPHVIEW_CANARY_NOTION_TARGET_ID)) {
    errors.push("GRAPHVIEW_CANARY_NOTION_TARGET_ID has an invalid format");
  }
  if (isConfigured(variables.GRAPHVIEW_CANARY_NOTION_TARGET_TYPE)
      && !["page", "database"].includes(variables.GRAPHVIEW_CANARY_NOTION_TARGET_TYPE)) {
    errors.push("GRAPHVIEW_CANARY_NOTION_TARGET_TYPE must be page or database");
  }
  if (isConfigured(variables.GRAPHVIEW_CANARY_OPENAI_MODEL)
      && !/^[A-Za-z0-9._:-]+$/.test(variables.GRAPHVIEW_CANARY_OPENAI_MODEL)) {
    errors.push("GRAPHVIEW_CANARY_OPENAI_MODEL has an invalid format");
  }
  for (const name of ["GRAPHVIEW_CANARY_SMTP_RECIPIENT", "GRAPHVIEW_CANARY_SMTP_FROM_ADDRESS"]) {
    if (isConfigured(variables[name]) && !EMAIL.test(variables[name])) errors.push(`${name} must be an email address`);
  }
  if (isConfigured(variables.GRAPHVIEW_CANARY_WEBHOOK_URL)
      && !isPublicHttps(variables.GRAPHVIEW_CANARY_WEBHOOK_URL)) {
    errors.push("GRAPHVIEW_CANARY_WEBHOOK_URL must be a public HTTPS URL without embedded credentials or fragments");
  }
  if (isConfigured(variables.GRAPHVIEW_CANARY_SMTP_HOST)
      && (!HOSTNAME.test(variables.GRAPHVIEW_CANARY_SMTP_HOST)
        || [".invalid", ".example", ".test", ".localhost", ".local"].some((suffix) =>
          variables.GRAPHVIEW_CANARY_SMTP_HOST.toLowerCase().endsWith(suffix)))) {
    errors.push("GRAPHVIEW_CANARY_SMTP_HOST must be a public hostname");
  }
  if (isConfigured(variables.GRAPHVIEW_CANARY_SMTP_PORT)) {
    const port = Number(variables.GRAPHVIEW_CANARY_SMTP_PORT);
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      errors.push("GRAPHVIEW_CANARY_SMTP_PORT must be an integer from 1 through 65535");
    }
  }
  if (isConfigured(variables.GRAPHVIEW_CANARY_SMTP_STARTTLS)
      && variables.GRAPHVIEW_CANARY_SMTP_STARTTLS !== "true") {
    errors.push("GRAPHVIEW_CANARY_SMTP_STARTTLS must be true for the production canary");
  }
  return errors;
}

function run(command, args, { input, label = command } = {}) {
  const result = spawnSync(command, args, {
    encoding: "utf8",
    input,
    maxBuffer: 10 * 1024 * 1024,
    stdio: [input === undefined ? "ignore" : "pipe", "pipe", "pipe"]
  });
  if (result.error) throw new Error(`${label} could not start: ${result.error.message}`);
  if (result.status !== 0) throw new Error(`${label} failed: ${(result.stderr || result.stdout).trim()}`);
  return result.stdout.trim();
}

function repositoryName() {
  return run("gh", ["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], { label: "repository lookup" });
}

function currentBranch() {
  return run("git", ["branch", "--show-current"], { label: "current branch lookup" });
}

function remoteCommit(ref) {
  const output = run("git", ["ls-remote", "--exit-code", "origin", `refs/heads/${ref}`], { label: "remote branch lookup" });
  const sha = output.split(/\s+/)[0];
  if (!/^[0-9a-f]{40}$/.test(sha)) throw new Error("Remote branch did not resolve to a full commit SHA.");
  return sha;
}

function configuredNames(kind) {
  const command = kind === "secret" ? "secret" : "variable";
  const rows = JSON.parse(run("gh", [command, "list", "--env", ENVIRONMENT, "--json", "name"], {
    label: `${command} inventory`
  }));
  return new Set(rows.map((row) => row.name));
}

function candidateEvidence(ref) {
  const repository = repositoryName();
  const sha = remoteCommit(ref);
  const runs = JSON.parse(run("gh", [
    "run", "list", "--workflow", "staging.yml", "--commit", sha, "--status", "success", "--limit", "20",
    "--json", "databaseId,headSha,url,conclusion,createdAt"
  ], { label: "staging run lookup" }));
  const runRow = runs.find((row) => row.headSha === sha && row.conclusion === "success");
  if (!runRow) return { repository, ref, sha, stagingRunId: null, stagingUrl: null, manifestArtifact: false };
  const artifacts = JSON.parse(run("gh", ["api", `repos/${repository}/actions/runs/${runRow.databaseId}/artifacts`], {
    label: "staging artifact lookup"
  }));
  const manifestArtifact = artifacts.artifacts.some((artifact) =>
    artifact.name === "graphview-candidate-image-manifest" && !artifact.expired
  );
  return {
    repository,
    ref,
    sha,
    stagingRunId: runRow.databaseId,
    stagingUrl: runRow.url,
    manifestArtifact
  };
}

function repositoryControls(repository) {
  const environment = JSON.parse(run("gh", ["api", `repos/${repository}/environments/${ENVIRONMENT}`], {
    label: "environment protection lookup"
  }));
  const reviewers = (environment.protection_rules ?? [])
    .filter((rule) => rule.type === "required_reviewers")
    .flatMap((rule) => rule.reviewers ?? [])
    .map((entry) => entry.reviewer?.login)
    .filter(Boolean)
    .sort();
  const requiredChecks = JSON.parse(run("gh", [
    "api", `repos/${repository}/branches/main/protection/required_status_checks`
  ], { label: "main branch protection lookup" }));
  const canaryContext = "Secret-backed connector, AI, and action canaries";
  return {
    environmentReviewers: reviewers,
    strictStatusChecks: requiredChecks.strict === true,
    canaryContextRequired: (requiredChecks.contexts ?? []).includes(canaryContext)
  };
}

function environmentStatus(ref) {
  const configuredSecrets = configuredNames("secret");
  const configuredVariables = configuredNames("variable");
  const missingSecrets = REQUIRED_SECRET_NAMES.filter((name) => !configuredSecrets.has(name));
  const missingVariables = REQUIRED_VARIABLE_NAMES.filter((name) => !configuredVariables.has(name));
  const smtpConfigured = OPTIONAL_SECRET_NAMES.filter((name) => configuredSecrets.has(name));
  const candidate = candidateEvidence(ref);
  const controls = repositoryControls(candidate.repository);
  return {
    environment: ENVIRONMENT,
    ref,
    secrets: {
      required: REQUIRED_SECRET_NAMES.length,
      configured: REQUIRED_SECRET_NAMES.length - missingSecrets.length,
      missing: missingSecrets,
      smtpAuthentication: smtpConfigured.length === 0 ? "disabled" : smtpConfigured.length === 2 ? "configured" : "incomplete"
    },
    variables: {
      required: REQUIRED_VARIABLE_NAMES.length,
      configured: REQUIRED_VARIABLE_NAMES.length - missingVariables.length,
      missing: missingVariables
    },
    candidate,
    controls,
    ready: missingSecrets.length === 0
      && missingVariables.length === 0
      && smtpConfigured.length !== 1
      && candidate.manifestArtifact
      && controls.environmentReviewers.length > 0
      && controls.strictStatusChecks
      && controls.canaryContextRequired
  };
}

async function loadConfiguration(file) {
  return parseConfigurationDocument(await readFile(file, "utf8"));
}

function assertValid(configuration) {
  const errors = validateCanaryConfiguration(configuration);
  if (errors.length > 0) throw new Error(`External canary configuration is invalid:\n- ${errors.join("\n- ")}`);
}

function assertDedicatedGitHubFixture(configuration, repository) {
  if (configuration.variables.GRAPHVIEW_CANARY_GITHUB_REPOSITORY.toLowerCase() === repository.toLowerCase()) {
    throw new Error("GRAPHVIEW_CANARY_GITHUB_REPOSITORY must be a dedicated fixture repository, not this repository.");
  }
}

async function configure(file) {
  const metadata = await stat(file);
  if (process.platform !== "win32" && (metadata.mode & 0o077) !== 0) {
    throw new Error("Canary configuration must not be readable or writable by group or other users; run chmod 600.");
  }
  const configuration = await loadConfiguration(file);
  assertValid(configuration);
  assertDedicatedGitHubFixture(configuration, repositoryName());
  const existingSecrets = configuredNames("secret");
  for (const name of ALL_SECRET_NAMES) {
    const value = configuration.secrets[name];
    if (!isConfigured(value)) {
      if (OPTIONAL_SECRET_NAMES.includes(name) && existingSecrets.has(name)) {
        run("gh", ["secret", "delete", name, "--env", ENVIRONMENT], {
          label: `optional secret removal for ${name}`
        });
      }
      continue;
    }
    run("gh", ["secret", "set", name, "--env", ENVIRONMENT], {
      input: value,
      label: `secret update for ${name}`
    });
  }
  for (const name of REQUIRED_VARIABLE_NAMES) {
    run("gh", ["variable", "set", name, "--env", ENVIRONMENT, "--body", configuration.variables[name]], {
      label: `variable update for ${name}`
    });
  }
  console.log(`Configured ${REQUIRED_SECRET_NAMES.length} required secret(s), ${REQUIRED_VARIABLE_NAMES.length} variable(s), and ${OPTIONAL_SECRET_NAMES.filter((name) => isConfigured(configuration.secrets[name])).length} optional SMTP secret(s) in ${ENVIRONMENT}.`);
}

function usage() {
  console.error("Usage: node scripts/manage-external-canaries.mjs <validate-env|validate-file|configure|status|dispatch> [config.json] [--ref branch]");
}

async function main() {
  const [command, argument, maybeRefFlag, maybeRef] = process.argv.slice(2);
  if (command === "validate-env") {
    const configuration = {
      secrets: Object.fromEntries(ALL_SECRET_NAMES.map((name) => [name, process.env[name] ?? ""])),
      variables: Object.fromEntries(REQUIRED_VARIABLE_NAMES.map((name) => [name, process.env[name] ?? ""]))
    };
    assertValid(configuration);
    if (process.env.GITHUB_REPOSITORY) assertDedicatedGitHubFixture(configuration, process.env.GITHUB_REPOSITORY);
    console.log("Protected external canary fixture configuration is valid.");
    return;
  }
  if (command === "validate-file" && argument) {
    assertValid(await loadConfiguration(argument));
    console.log("External canary configuration file is valid; values were not printed.");
    return;
  }
  if (command === "configure" && argument) {
    await configure(argument);
    return;
  }
  if (["status", "dispatch"].includes(command)) {
    const ref = argument === "--ref" ? maybeRefFlag : maybeRefFlag === "--ref" ? maybeRef : argument || currentBranch();
    if (!ref) throw new Error("A remote branch ref is required.");
    const status = environmentStatus(ref);
    console.log(JSON.stringify(status, null, 2));
    if (command === "dispatch") {
      if (!status.ready) throw new Error("External canary environment or staging evidence is incomplete; dispatch refused.");
      run("gh", ["workflow", "run", "external-canaries.yml", "--ref", ref], { label: "external canary dispatch" });
      console.log(`Dispatched protected external canaries for ${ref} at ${status.candidate.sha}.`);
    }
    return;
  }
  usage();
  process.exitCode = 2;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
