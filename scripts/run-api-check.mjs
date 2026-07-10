import { spawn } from "node:child_process";

for (const [command, args] of [
  ["uv", ["run", "--package", "graphview-api", "python", "scripts/check-openapi-drift.py"]],
  ["node", ["scripts/check-generated-client.mjs"]]
]) {
  await new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: "inherit" });
    child.on("error", reject);
    child.on("exit", (code) => code === 0 ? resolve() : reject(new Error(`${command} failed with ${code}`)));
  });
}
