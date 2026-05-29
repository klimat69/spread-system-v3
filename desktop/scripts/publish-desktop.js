#!/usr/bin/env node
/**
 * Build desktop installers, verify updater metadata, then publish to GitHub.
 * macOS: separate x64 (Intel) and arm64 (Apple Silicon) builds.
 */
const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const desktopDir = path.resolve(__dirname, "..");
const distDir = path.resolve(desktopDir, "../installer/dist");
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

function collectPublishFiles(targetPlatform) {
  if (!fs.existsSync(distDir)) {
    return [];
  }
  return fs
    .readdirSync(distDir)
    .filter((name) => {
      if (targetPlatform === "mac") {
        return (
          name === "latest-mac.yml" ||
          /^spread-system-v3-(x64|arm64)\.(zip|dmg|blockmap)$/.test(name)
        );
      }
      return name === "latest.yml" || /^spread-system-v3-setup\.(exe|blockmap)$/.test(name);
    })
    .map((name) => path.join(distDir, name));
}

if (platform !== "mac" && platform !== "win") {
  console.error("Usage: node publish-desktop.js <mac|win>");
  process.exit(1);
}

run("npm", ["run", "build:backend-runtime"], "backend runtime");
run("npm", ["run", "verify:backend-runtime"], "backend runtime verify");
run("npm", ["run", `verify:target:${platform}`], "host target");

if (platform === "mac") {
  for (const arch of ["x64", "arm64"]) {
    run(
      "npx",
      ["electron-builder", ...configs, "--mac", `--${arch}`, "--publish", "never"],
      `electron-builder mac ${arch}`
    );
  }
} else {
  run(
    "npx",
    ["electron-builder", ...configs, "--win", "--publish", "never"],
    "electron-builder win build"
  );
}

run("node", ["./scripts/verify-update-artifacts.js", platform], "update artifact verify");

const publishFiles = collectPublishFiles(platform);
if (!publishFiles.length) {
  console.error("publish-desktop: no artifacts to publish in installer/dist");
  if (fs.existsSync(distDir)) {
    console.error(`found: ${fs.readdirSync(distDir).join(", ")}`);
  }
  process.exit(1);
}

const publishArgs = ["electron-builder", "publish", ...configs];
for (const file of publishFiles) {
  publishArgs.push("-f", file);
}
run("npx", publishArgs, `electron-builder publish ${platform}`);

console.log(`publish-desktop: ${platform} published (${publishFiles.length} files)`);
