#!/usr/bin/env node
/**
 * Build desktop installers, verify updater metadata, then publish to GitHub.
 * Fails the release if artifacts do not match electron-updater expectations.
 */
const { spawnSync } = require("child_process");
const path = require("path");

const desktopDir = path.resolve(__dirname, "..");
const platform = (process.argv[2] || "").toLowerCase();
const configs = [
  "--config",
  "../installer/electron-builder.json",
  "--config",
  "../installer/electron-builder.github.json"
];

function run(command, args, label) {
  const result = spawnSync(command, args, { cwd: desktopDir, stdio: "inherit", shell: false });
  if (result.status !== 0) {
    console.error(`publish-desktop: ${label} failed (exit ${result.status ?? 1})`);
    process.exit(result.status ?? 1);
  }
}

if (platform !== "mac" && platform !== "win") {
  console.error("Usage: node publish-desktop.js <mac|win>");
  process.exit(1);
}

const targetFlag = platform === "mac" ? "--mac" : "--win";

run("npm", ["run", "build:backend-runtime"], "backend runtime");
run("npm", ["run", "verify:backend-runtime"], "backend runtime verify");
run("npm", ["run", `verify:target:${platform}`], "host target");

run(
  "npx",
  ["electron-builder", ...configs, targetFlag, "--publish", "never"],
  `electron-builder ${platform} build`
);

run("node", ["./scripts/verify-update-artifacts.js", platform], "update artifact verify");

const distDir = path.resolve(desktopDir, "../installer/dist");
run(
  "npx",
  ["electron-builder", "publish", ...configs, `--path=${distDir}`],
  `electron-builder publish ${platform}`
);

console.log(`publish-desktop: ${platform} published successfully`);
