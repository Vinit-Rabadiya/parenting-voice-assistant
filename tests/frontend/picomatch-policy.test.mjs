import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const workspace = fileURLToPath(new URL("../../", import.meta.url));
const frontend = resolve(workspace, "frontend");
const require = createRequire(join(frontend, "package.json"));
const { disableExtglobs } = require("../scripts/disable-picomatch-extglobs.cjs");
disableExtglobs(frontend);
const picomatch = require("picomatch");

test("Vite, Vitest and tinyglobby resolve protected Picomatch parsers", () => {
  for (const dependency of ["vite", "vitest", "tinyglobby"]) {
    const fromDependency = createRequire(require.resolve(dependency));
    const matcher = fromDependency("picomatch");
    const state = matcher.parse("+(*a)", { noext: false, noextglob: false, regex: true, maxExtglobRecursion: false });
    assert.equal(state.tokens.some(token => token.extglob === true), false, dependency);
  }
});

test("ordinary test, source and exclusion patterns retain their matching", () => {
  for (const [pattern, input, expected, options = {}] of [
    ["tests/frontend/**/*.test.jsx", "tests/frontend/GuidanceWorkspace.test.jsx", true],
    ["tests/frontend/**/*.test.jsx", "tests/frontend/nested/Account.test.jsx", true],
    ["tests/frontend/**/*.test.jsx", "tests/frontend/helper.jsx", false],
    ["**/*.{js,jsx}", "src/App.jsx", true],
    ["**/*.{js,jsx}", "src/index.css", false],
    ["**/node_modules/**", "frontend/node_modules/react/index.js", true],
    ["**/*.js", ".hidden/index.js", false],
    ["**/*.js", ".hidden/index.js", true, { dot: true }],
    ["tests/frontend/**/*.test.jsx", "tests\\frontend\\Account.test.jsx", true, { windows: true }],
  ]) assert.equal(picomatch.isMatch(input, pattern, options), expected, `${pattern}: ${input}`);
});

test("affected repetitions stay disabled even when callers re-enable options", () => {
  // A child-process deadline prevents a regression from hanging the test runner.
  const probe = `
    const assert = require('node:assert/strict');
    const pm = require(process.argv[1]);
    for (const pattern of ['+(*a)', '+(*)', '*(*a)', '*(*)', '+(*)c', '+(*a|*b)', '+(*[ab])', '+(a*b)', '*(b|*a)']) {
      for (const fastpaths of [true, false]) {
        const options = { noext: false, noextglob: false, regex: true, maxExtglobRecursion: false, fastpaths };
        assert.equal(pm.parse(pattern, options).tokens.some(token => token.extglob === true), false);
        for (const input of ['a'.repeat(256) + '/', '+' + 'a'.repeat(256) + '!']) {
          pm.isMatch(input, pattern, options);
          pm.makeRe(pattern, options).test(input);
        }
      }
    }
  `;
  const result = spawnSync(process.execPath, ["-e", probe, require.resolve("picomatch")], {
    timeout: 3000, encoding: "utf8", windowsHide: true,
  });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
});

test("installation policy is repeatable and refuses unreviewed parser changes", () => {
  const temporaryRoot = resolve(workspace, "tmp");
  mkdirSync(temporaryRoot, { recursive: true });
  const fixture = mkdtempSync(join(temporaryRoot, "picomatch-policy-"));
  assert.equal(dirname(fixture), temporaryRoot);
  const dependency = join(fixture, "node_modules/picomatch");
  const parser = join(dependency, "lib/parse.js");
  try {
    mkdirSync(dirname(parser), { recursive: true });
    const packageFile = join(dependency, "package.json");
    const protectedParser = readFileSync(join(dirname(require.resolve("picomatch")), "lib/parse.js"), "utf8");
    const originalParser = protectedParser.replaceAll(
      "  // Project policy: disable extglobs and regex quantifiers (CVE-2026-112366).\n  const opts = { ...options, noext: true, noextglob: true, regex: false };",
      "  const opts = { ...options };",
    );
    writeFileSync(join(fixture, "package-lock.json"), JSON.stringify({ packages: { "node_modules/picomatch": { version: "4.0.7" } } }));
    writeFileSync(packageFile, JSON.stringify({ name: "picomatch", version: "4.0.7" }));
    writeFileSync(parser, originalParser);
    assert.equal(disableExtglobs(fixture), 1);
    assert.equal(readFileSync(parser, "utf8"), protectedParser);
    assert.equal(disableExtglobs(fixture), 1);
    writeFileSync(parser, protectedParser + "\n// Unexpected source change.\n");
    assert.throws(() => disableExtglobs(fixture), /differs from the reviewed release/);
    writeFileSync(parser, protectedParser);
    writeFileSync(packageFile, JSON.stringify({ name: "picomatch", version: "4.0.8" }));
    assert.throws(() => disableExtglobs(fixture), /version changed/);
  } finally {
    // This directory and all its files were created by this test.
    assert.ok(fixture.startsWith(temporaryRoot + sep + "picomatch-policy-"));
    rmSync(fixture, { recursive: true, force: true });
  }
});
