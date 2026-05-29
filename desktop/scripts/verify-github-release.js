#!/usr/bin/env node
/**
 * CI check: GitHub Release for tag has updater artifacts for macOS and Windows.
 */
const https = require("https");

const owner = process.env.GH_OWNER || "klimat69";
const repo = process.env.GH_REPO || "spread-system-v3";
const tag = process.env.RELEASE_TAG || process.argv[2];
if (!tag) {
  console.error("verify-github-release: set RELEASE_TAG or pass tag argument");
  process.exit(1);
}

function getText(url) {
  return new Promise((resolve, reject) => {
    const headers = { "User-Agent": "spread-system-v3-release-verify" };
    if (process.env.GH_TOKEN) headers.Authorization = `Bearer ${process.env.GH_TOKEN}`;
    https
      .get(url, { headers }, (res) => {
        let body = "";
        res.on("data", (chunk) => {
          body += chunk;
        });
        res.on("end", () => {
          if (res.statusCode && res.statusCode >= 400) {
            reject(new Error(`HTTP ${res.statusCode} for ${url}`));
            return;
          }
          resolve(body);
        });
      })
      .on("error", reject);
  });
}

function getJson(url) {
  return getText(url).then((body) => JSON.parse(body));
}

async function main() {
  const release = await getJson(`https://api.github.com/repos/${owner}/${repo}/releases/tags/${tag}`);
  const names = new Set((release.assets || []).map((asset) => asset.name));
  const required = [
    "latest-mac.yml",
    "latest.yml",
    "spread-system-v3-x64.zip",
    "spread-system-v3-arm64.zip",
    "spread-system-v3-setup.exe"
  ];
  const missing = required.filter((name) => !names.has(name));
  if (missing.length) {
    console.error(`verify-github-release: release ${tag} missing assets:\n- ${missing.join("\n- ")}`);
    console.error(`found: ${[...names].sort().join(", ")}`);
    process.exit(1);
  }

  const macYml = await getText(`https://github.com/${owner}/${repo}/releases/download/${tag}/latest-mac.yml`);
  if (!macYml.includes("spread-system-v3-x64.zip") || !macYml.includes("spread-system-v3-arm64.zip")) {
    console.error("verify-github-release: latest-mac.yml must reference x64 and arm64 zip files");
    process.exit(1);
  }

  const winYml = await getText(`https://github.com/${owner}/${repo}/releases/download/${tag}/latest.yml`);
  if (!winYml.includes("spread-system-v3-setup.exe")) {
    console.error("verify-github-release: latest.yml must reference spread-system-v3-setup.exe");
    process.exit(1);
  }

  console.log(`verify-github-release: ${tag} OK`);
}

main().catch((error) => {
  console.error(`verify-github-release: ${error.message}`);
  process.exit(1);
});
