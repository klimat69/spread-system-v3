#!/usr/bin/env node
/**
 * Build latest-mac.yml for electron-updater after separate x64/arm64 zip builds.
 */
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const distDir = path.resolve(__dirname, "../../installer/dist");
const version = require("../package.json").version;

function sha512Base64(filePath) {
  const hash = crypto.createHash("sha512");
  hash.update(fs.readFileSync(filePath));
  return hash.digest("base64");
}

function main() {
  const files = [];
  for (const arch of ["x64", "arm64"]) {
    const zipName = `spread-system-v3-${arch}.zip`;
    const zipPath = path.join(distDir, zipName);
    if (!fs.existsSync(zipPath)) {
      console.error(`generate-latest-mac-yml: missing ${zipName}`);
      process.exit(1);
    }
    const stat = fs.statSync(zipPath);
    files.push({
      url: zipName,
      sha512: sha512Base64(zipPath),
      size: stat.size
    });
  }

  const primary = files[0];
  const lines = [
    `version: ${version}`,
    "files:",
    ...files.flatMap((file) => [
      `  - url: ${file.url}`,
      `    sha512: ${file.sha512}`,
      `    size: ${file.size}`
    ]),
    `path: ${primary.url}`,
    `sha512: ${primary.sha512}`,
    `releaseDate: '${new Date().toISOString()}'`,
    ""
  ];

  fs.writeFileSync(path.join(distDir, "latest-mac.yml"), lines.join("\n"));
  console.log(`generate-latest-mac-yml: wrote latest-mac.yml (${version}, x64 + arm64)`);
}

main();
