import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import process from "node:process";

const root = process.cwd();
const temporary = await mkdtemp(path.join(tmpdir(), "graphview-api-client-"));
const generated = path.join(temporary, "schema.ts");
try {
  execFileSync("pnpm", ["exec", "openapi-typescript", "services/api/openapi.yaml", "-o", generated], {
    cwd: root,
    stdio: "ignore"
  });
  const [actual, expected] = await Promise.all([
    readFile(path.join(root, "packages/api-client/src/schema.ts"), "utf8"),
    readFile(generated, "utf8")
  ]);
  if (actual !== expected) throw new Error("Generated TypeScript API client drift detected. Run pnpm api:generate.");
  console.log("Generated TypeScript API client is current.");
} finally {
  await rm(temporary, { recursive: true, force: true });
}
