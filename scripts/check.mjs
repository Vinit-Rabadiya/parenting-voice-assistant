// npm run check and the pre-push hook use this runner to verify python and frontend code.
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
const mode = process.argv[2] ?? "--all";
if (process.argv.length > 3 || !["--all", "--lint", "--tests"].includes(mode)) {
  console.error("Usage: node scripts/check.mjs [--all|--lint|--tests]");
  process.exit(1);
}

if (!npmPath) {
  console.error("Script must be executed within npm context (e.g., npm run check)");
  process.exit(1);
}

function runCheck(label, command, args) {
  // inherit terminal output and stop the whole sequence when a check fails.
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

// check python code with ruff.
if (mode !== "--tests") {
  runCheck("Python lint", pythonCommand, ["-m", "ruff", "check", "."]);
}

// run backend tests with pytest.
if (mode !== "--lint") {
  runCheck("Python tests", pythonCommand, ["-m", "pytest"]);
}

// check frontend code with eslint.
if (mode !== "--tests") runCheck("Frontend lint", process.execPath, [
  npmPath,
  "--prefix",
  "frontend",
  "run",
  "lint",
]);

// check binary audio helpers and react request lifecycle behavior.
if (mode !== "--lint") runCheck("Frontend tests", process.execPath, [npmPath, "--prefix", "frontend", "run", "test"]);

// test building the frontend with vite.
if (mode === "--all") runCheck("Frontend build", process.execPath, [
  npmPath,
  "--prefix",
  "frontend",
  "run",
  "build",
]);

console.log(mode === "--all" ? "\nAll configured checks passed." : `\n${mode === "--lint" ? "Lint" : "Test"} checks passed.`);
