import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";
import { join } from "node:path";

const projectRoot = fileURLToPath(new URL("../", import.meta.url));
const pythonRelativePath =
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python";

const localPython = [".venv", "venv"]
  .map((folder) => join(projectRoot, folder, pythonRelativePath))
  .find((candidate) => existsSync(candidate));

const pythonCommand = localPython ?? "python";
const npmPath = process.env.npm_execpath;

if (!npmPath) {
  console.error("Run this script using: npm run check");
  process.exit(1);
}

function runCheck(label, command, args) {
  console.log(`\n--- ${label} ---`);

  const result = spawnSync(command, args, {
    cwd: projectRoot,
    stdio: "inherit",
    shell: false,
  });

  if (result.error) {
    console.error(`Could not start ${label}: ${result.error.message}`);
    process.exit(1);
  }

  if (result.status !== 0) {
    console.error(`${label} failed. Stopping checks.`);
    process.exit(result.status ?? 1);
  }
}

runCheck("Python lint", pythonCommand, ["-m", "ruff", "check", "."]);

runCheck("Frontend lint", process.execPath, [
  npmPath,
  "--prefix",
  "frontend",
  "run",
  "lint",
]);

runCheck("Frontend build", process.execPath, [
  npmPath,
  "--prefix",
  "frontend",
  "run",
  "build",
]);

console.log("\nAll configured checks passed.");
