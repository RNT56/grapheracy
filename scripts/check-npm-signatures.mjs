import { readFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";

const root = process.cwd();
const [workspaceConfig, lockfile] = await Promise.all([
  readFile(path.join(root, "pnpm-workspace.yaml"), "utf8"),
  readFile(path.join(root, "pnpm-lock.yaml"), "utf8"),
]);

const requiredPolicies = [
  /^minimumReleaseAge: 1440$/m,
  /^minimumReleaseAgeStrict: true$/m,
  /^minimumReleaseAgeIgnoreMissingTime: false$/m,
  /^trustPolicy: no-downgrade$/m,
  /^blockExoticSubdeps: true$/m,
];

for (const policy of requiredPolicies) {
  if (!policy.test(workspaceConfig)) {
    throw new Error(`required pnpm supply-chain policy is missing: ${policy.source}`);
  }
}

if (!/^lockfileVersion: '9\.0'$/m.test(lockfile)) {
  throw new Error("pnpm-lock.yaml must use the reviewed lockfileVersion 9.0 format");
}

const resolutionLines = lockfile
  .split("\n")
  .filter((line) => /^ {4}resolution:/.test(line));

if (resolutionLines.length === 0) {
  throw new Error("pnpm-lock.yaml contains no registry package resolutions");
}

const unsignedResolutions = resolutionLines.filter(
  (line) => !/resolution: \{integrity: sha512-[A-Za-z0-9+/]+={0,2}\}$/.test(line),
);
if (unsignedResolutions.length > 0) {
  throw new Error(
    `pnpm-lock.yaml contains ${unsignedResolutions.length} package resolution(s) without a sha512 integrity digest`,
  );
}

if (/\b(?:git\+|git:|github:|https?:\/\/)[^\s}"']+/i.test(lockfile)) {
  throw new Error("pnpm-lock.yaml contains an unreviewed exotic or URL dependency");
}

await new Promise((resolve, reject) => {
  const child = spawn(
    "pnpm",
    ["install", "--frozen-lockfile", "--lockfile-only", "--offline", "--ignore-scripts"],
    { cwd: root, stdio: "inherit" },
  );
  child.on("exit", (code) => {
    if (code === 0) resolve();
    else reject(new Error(`pnpm frozen offline lock verification failed with exit code ${code}`));
  });
  child.on("error", reject);
});

console.log(
  `pnpm supply-chain verification passed (${resolutionLines.length} sha512-pinned registry packages; no exotic dependencies).`,
);
