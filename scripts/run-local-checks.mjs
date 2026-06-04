import { spawn } from "node:child_process";

const checks = {
  "doc-links": ["node", ["scripts/check-doc-links.mjs"]],
  "doc-freshness": ["node", ["scripts/check-doc-freshness.mjs"]],
  "lint:docs": ["node", ["scripts/run-local-checks.mjs", "doc-links", "doc-freshness"]],
  "lint:metadata": ["node", ["scripts/check-workspace-metadata.mjs"]],
  lint: ["node", ["scripts/run-local-checks.mjs", "lint:docs", "lint:metadata"]],
  "security:local": ["node", ["scripts/check-security-policy.mjs"]],
  "security:licenses": ["node", ["scripts/check-license-policy.mjs"]],
  "changelog:check": ["node", ["scripts/check-changelog.mjs"]],
  typecheck: ["node", ["scripts/run-workspace-scripts.mjs", "typecheck"]],
  test: ["node", ["scripts/run-workspace-scripts.mjs", "test"]]
};

const selected = process.argv.slice(2);
if (selected.length === 0) {
  console.error("Pass at least one check name.");
  process.exit(1);
}

for (const check of selected) {
  const command = checks[check];
  if (!command) {
    console.error(`Unknown check: ${check}`);
    process.exit(1);
  }

  const [bin, args] = command;
  console.log(`\n> ${check}`);
  await new Promise((resolve, reject) => {
    const child = spawn(bin, args, { stdio: "inherit" });
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${check} failed with exit code ${code}`));
    });
    child.on("error", reject);
  }).catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}
