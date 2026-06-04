import { readFile } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const packageJson = JSON.parse(await readFile(path.join(root, "package.json"), "utf8"));
const security = await readFile(path.join(root, "docs/03-security.md"), "utf8");

const failures = [];

if (packageJson.license !== "UNLICENSED") {
  failures.push("root package must stay UNLICENSED until release licensing is approved");
}

for (const phrase of ["License compatibility", "Dependency Approval Checklist", "Lockfile diff"]) {
  if (!security.includes(phrase)) failures.push(`docs/03-security.md missing ${phrase}`);
}

if (failures.length > 0) {
  console.error("License policy check failed:");
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log("License policy check passed.");
