const target = process.argv[2];

if (!target) {
  console.error("[verify-host-target] Missing target argument (mac|win|linux).");
  process.exit(1);
}

const host = process.platform;
const normalizedHost = host === "darwin" ? "mac" : host === "win32" ? "win" : host === "linux" ? "linux" : host;

if (normalizedHost !== target) {
  console.error(
    `[verify-host-target] Refusing to build ${target} installer on ${normalizedHost}. ` +
      "Backend runtime is OS-specific and must be built on the target OS."
  );
  process.exit(1);
}

console.log(`[verify-host-target] OK: host=${normalizedHost}, target=${target}`);
