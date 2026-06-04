import { stat } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";

try {
  await stat(path.join(process.cwd(), "package-lock.json"));
} catch {
  console.log("npm audit signatures skipped: package-lock.json is not present in this pnpm workspace.");
  process.exit(0);
}

await new Promise((resolve, reject) => {
  const child = spawn("npm", ["audit", "signatures"], { stdio: "inherit" });
  child.on("exit", (code) => {
    if (code === 0) resolve();
    else reject(new Error(`npm audit signatures failed with exit code ${code}`));
  });
  child.on("error", reject);
}).catch((error) => {
  console.error(error.message);
  process.exit(1);
});
