import assert from "node:assert/strict";
import test from "node:test";

import {
  OPTIONAL_SECRET_NAMES,
  REQUIRED_SECRET_NAMES,
  REQUIRED_VARIABLE_NAMES,
  parseConfigurationDocument,
  validateCanaryConfiguration
} from "./manage-external-canaries.mjs";

function validConfiguration() {
  return {
    secrets: {
      GRAPHVIEW_CANARY_GITHUB_TOKEN: "github-token-value",
      GRAPHVIEW_CANARY_GOOGLE_CLIENT_ID: "google-client-id",
      GRAPHVIEW_CANARY_GOOGLE_CLIENT_SECRET: "google-client-secret",
      GRAPHVIEW_CANARY_GOOGLE_REFRESH_TOKEN: "google-refresh-token",
      GRAPHVIEW_CANARY_NOTION_TOKEN: "notion-token-value",
      GRAPHVIEW_CANARY_OPENAI_API_KEY: "openai-key-value",
      GRAPHVIEW_CANARY_SMTP_USERNAME: "smtp-user",
      GRAPHVIEW_CANARY_SMTP_PASSWORD: "smtp-password",
      GRAPHVIEW_CANARY_WEBHOOK_SECRET: "0123456789abcdef0123456789abcdef"
    },
    variables: {
      GRAPHVIEW_CANARY_GITHUB_REPOSITORY: "fixture/graphview-canary",
      GRAPHVIEW_CANARY_GOOGLE_FOLDER_ID: "folder_123",
      GRAPHVIEW_CANARY_NOTION_TARGET_ID: "0123456789abcdef0123456789abcdef",
      GRAPHVIEW_CANARY_NOTION_TARGET_TYPE: "page",
      GRAPHVIEW_CANARY_OPENAI_MODEL: "gpt-5-mini",
      GRAPHVIEW_CANARY_SMTP_RECIPIENT: "canary@example.com",
      GRAPHVIEW_CANARY_WEBHOOK_URL: "https://canary.example.com/graphview",
      GRAPHVIEW_CANARY_SMTP_HOST: "smtp.example.com",
      GRAPHVIEW_CANARY_SMTP_PORT: "587",
      GRAPHVIEW_CANARY_SMTP_STARTTLS: "true",
      GRAPHVIEW_CANARY_SMTP_FROM_ADDRESS: "graphview@example.com"
    }
  };
}

test("validates a complete protected fixture without exposing values", () => {
  assert.deepEqual(validateCanaryConfiguration(validConfiguration()), []);
  assert.equal(REQUIRED_SECRET_NAMES.length, 7);
  assert.equal(OPTIONAL_SECRET_NAMES.length, 2);
  assert.equal(REQUIRED_VARIABLE_NAMES.length, 11);
});

test("reports missing fixture names and rejects partial SMTP authentication", () => {
  const configuration = validConfiguration();
  configuration.secrets.GRAPHVIEW_CANARY_GITHUB_TOKEN = "";
  configuration.secrets.GRAPHVIEW_CANARY_SMTP_PASSWORD = "";
  const errors = validateCanaryConfiguration(configuration);
  assert(errors.includes("GRAPHVIEW_CANARY_GITHUB_TOKEN is required"));
  assert(errors.some((error) => error.includes("must be configured together")));
  assert(errors.every((error) => !error.includes("github-token-value")));
});

test("rejects local webhook destinations, weak secrets, and insecure SMTP", () => {
  const configuration = validConfiguration();
  configuration.secrets.GRAPHVIEW_CANARY_WEBHOOK_SECRET = "short";
  configuration.variables.GRAPHVIEW_CANARY_WEBHOOK_URL = "https://127.0.0.1/hook";
  configuration.variables.GRAPHVIEW_CANARY_SMTP_STARTTLS = "false";
  const errors = validateCanaryConfiguration(configuration);
  assert.equal(errors.length, 3);
});

test("rejects reserved and literal-IP webhook receivers", () => {
  const reserved = validConfiguration();
  reserved.variables.GRAPHVIEW_CANARY_WEBHOOK_URL = "https://canary.example.invalid/hook";
  assert(validateCanaryConfiguration(reserved).some((error) => error.includes("public HTTPS URL")));

  const literalIp = validConfiguration();
  literalIp.variables.GRAPHVIEW_CANARY_WEBHOOK_URL = "https://203.0.113.10/hook";
  assert(validateCanaryConfiguration(literalIp).some((error) => error.includes("public HTTPS URL")));
});

test("configuration parser rejects unknown names instead of silently dropping typos", () => {
  const configuration = validConfiguration();
  configuration.secrets.GRAPHVIEW_CANARY_GITHUB_T0KEN = "typo";
  assert.throws(
    () => parseConfigurationDocument(JSON.stringify(configuration)),
    /GRAPHVIEW_CANARY_GITHUB_T0KEN/
  );
});

test("configuration parser rejects unknown top-level sections", () => {
  const configuration = validConfiguration();
  configuration.secret = {};
  assert.throws(() => parseConfigurationDocument(JSON.stringify(configuration)), /section\(s\): secret/);
});

test("rejects multiline protected values", () => {
  const configuration = validConfiguration();
  configuration.secrets.GRAPHVIEW_CANARY_OPENAI_API_KEY = "first-line\nsecond-line";
  assert(validateCanaryConfiguration(configuration).some((error) => error.includes("single-line")));
});
