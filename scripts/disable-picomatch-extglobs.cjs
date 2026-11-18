// Keep Vite/Vitest file matching while disabling Picomatch's affected extglobs.
// Pin the source checks so an upstream change requires a fresh review.
const { createHash } = require("node:crypto");
const { readFileSync, writeFileSync } = require("node:fs");
const { resolve, sep } = require("node:path");

const originalHash = "4e1e05447668aa1e94366c5516a2bcd8f5fff800cc92b1d0cd7d77703b8618c4";
const originalOptions = "  const opts = { ...options };";
const protectedOptions = [
  "  // Project policy: disable extglobs and regex quantifiers (CVE-2026-112366).",
  "  const opts = { ...options, noext: true, noextglob: true, regex: false };",
].join("\n");
const digest = (source) => createHash("sha256").update(source).digest("hex");

function disableExtglobs(frontendRoot = resolve(__dirname, "../frontend")) {
  const lock = JSON.parse(readFileSync(resolve(frontendRoot, "package-lock.json"), "utf8"));
  const packages = Object.entries(lock.packages).filter(([name]) => name.endsWith("/node_modules/picomatch") || name === "node_modules/picomatch");
  if (!packages.length) throw new Error("Picomatch is missing from the lockfile; review the pattern policy.");

  // Check every locked copy before modifying any of them.
  const changes = packages.map(([name, entry]) => {
    const directory = resolve(frontendRoot, name);
    if (!directory.startsWith(resolve(frontendRoot, "node_modules") + sep)) {
      throw new Error("Unexpected Picomatch dependency path.");
    }
    const installed = JSON.parse(readFileSync(resolve(directory, "package.json"), "utf8"));
    if (entry.version !== "4.0.7" || installed.name !== "picomatch" || installed.version !== "4.0.7") {
      throw new Error("Picomatch version changed; review the pattern policy before running frontend tools.");
    }
    const file = resolve(directory, "lib/parse.js");
    const source = readFileSync(file, "utf8").replace(/\r\n/g, "\n");
    // Reconstruct the verified release from an already protected installation.
    const original = source.replaceAll(protectedOptions, originalOptions);
    if (digest(original) !== originalHash || original.split(originalOptions).length !== 3) {
      throw new Error("Picomatch parser differs from the reviewed release; refusing to run frontend tools.");
    }
    const updated = original.replaceAll(originalOptions, protectedOptions);
    if (source !== original && source !== updated) {
      throw new Error("Picomatch pattern policy is only partially applied.");
    }
    return { file, source, updated };
  });
  for (const { file, source, updated } of changes) {
    if (source !== updated) writeFileSync(file, updated);
  }
  return changes.length;
}

if (require.main === module) {
  try {
    disableExtglobs();
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}

module.exports = { disableExtglobs };
