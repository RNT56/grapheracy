import { access } from "node:fs/promises";
import { constants } from "node:fs";
import { delimiter, join } from "node:path";
import { spawn } from "node:child_process";

const gitleaks = await findExecutable("gitleaks");
if (gitleaks) {
  await run(gitleaks, ["detect", "--source", ".", "--no-git"]);
  process.exit(0);
}

const go = await findExecutable("go");
if (go) {
  await run(go, ["run", "github.com/zricethezav/gitleaks/v8@latest", "detect", "--source", ".", "--no-git"]);
  process.exit(0);
}

console.error("Secret scan requires either gitleaks or go for the official Gitleaks module fallback.");
process.exit(1);

async function findExecutable(name) {
  for (const directory of (process.env.PATH || "").split(delimiter)) {
    const candidate = join(directory, name);
    try {
      await access(candidate, constants.X_OK);
      return candidate;
    } catch {
      continue;
    }
  }
  return null;
}

async function run(command, args) {
  await new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: "inherit" });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${command} ${args.join(" ")} failed with exit code ${code}`));
    });
  }).catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}
