import { readdir, readFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";
import { delimiter } from "node:path";

const scriptName = process.argv[2];
if (!scriptName) {
  console.error("Usage: node scripts/run-workspace-scripts.mjs <script>");
  process.exit(1);
}

const roots = ["apps", "services", "packages"];
const workspacePackages = [];

for (const rootDir of roots) {
  const entries = await readdir(rootDir, { withFileTypes: true });
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const packagePath = path.join(rootDir, entry.name, "package.json");
    try {
      const pkg = JSON.parse(await readFile(packagePath, "utf8"));
      if (pkg.scripts?.[scriptName]) {
        workspacePackages.push({ dir: path.dirname(packagePath), name: pkg.name, command: pkg.scripts[scriptName] });
      }
    } catch {
      continue;
    }
  }
}

for (const pkg of workspacePackages) {
  console.log(`\n> ${pkg.name} ${scriptName}`);
  await new Promise((resolve, reject) => {
    const binPaths = [
      path.join(process.cwd(), pkg.dir, "node_modules", ".bin"),
      path.join(process.cwd(), "node_modules", ".bin"),
      process.env.PATH ?? ""
    ];
    const child = spawn(pkg.command, {
      cwd: pkg.dir,
      shell: true,
      stdio: "inherit",
      env: { ...process.env, PATH: binPaths.join(delimiter) }
    });
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${pkg.name} ${scriptName} failed with exit code ${code}`));
    });
    child.on("error", reject);
  }).catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
}

console.log(`\nWorkspace ${scriptName} completed for ${workspacePackages.length} package(s).`);
