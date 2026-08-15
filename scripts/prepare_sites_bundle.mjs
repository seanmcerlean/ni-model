import { copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outputRoot = resolve(projectRoot, "dist");

await mkdir(resolve(outputRoot, "server"), { recursive: true });
await mkdir(resolve(outputRoot, ".openai"), { recursive: true });
await copyFile(
  resolve(projectRoot, "sites/server/index.js"),
  resolve(outputRoot, "server/index.js"),
);
await copyFile(
  resolve(projectRoot, ".openai/hosting.json"),
  resolve(outputRoot, ".openai/hosting.json"),
);
