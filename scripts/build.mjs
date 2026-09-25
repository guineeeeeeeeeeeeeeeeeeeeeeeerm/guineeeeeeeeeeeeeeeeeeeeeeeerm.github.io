import { build as astroBuild } from "astro";
import { cp, mkdir, mkdtemp, rename, rm, stat, symlink, unlink, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const projectRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));

async function copyTree(source, destination) {
  await cp(source, destination, { recursive: true, force: true });
}

async function copyContentImages(contentRoot, outputRoot) {
  const source = path.join(contentRoot, "images");
  try {
    if ((await stat(source)).isDirectory()) {
      await copyTree(source, path.join(outputRoot, "images"));
    }
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
}

async function install(staging, docs) {
  const backup = `${docs}.backup-${process.pid}`;
  let moved = false;
  try {
    await rm(backup, { recursive: true, force: true });
    try {
      await rename(docs, backup);
      moved = true;
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
    await rename(staging, docs);
    if (moved) await rm(backup, { recursive: true, force: true });
  } catch (error) {
    if (moved) {
      try {
        await rm(docs, { recursive: true, force: true });
        await rename(backup, docs);
      } catch {
        // Keep the original error; the normal path restores the old tree.
      }
    }
    throw error;
  }
}

async function build() {
  const root = process.cwd();
  const contentRoot = path.join(root, "content");
  const docs = path.join(root, "docs");
  const workspace = await mkdtemp(path.join(root, ".docs-build-"));
  const staging = path.join(workspace, "output");
  await mkdir(staging);
  let installed = false;
  try {
    await symlink(path.join(projectRoot, "node_modules"), path.join(workspace, "node_modules"), "dir");
    process.env.GUIN_CONTENT_ROOT = contentRoot;
    process.env.ASTRO_TELEMETRY_DISABLED = "1";
    await astroBuild({
      root: projectRoot,
      srcDir: path.join(projectRoot, "src"),
      publicDir: path.join(projectRoot, "public"),
      outDir: staging,
      cacheDir: path.join(workspace, ".astro"),
      logLevel: "silent",
    });
    await unlink(path.join(workspace, "node_modules"));
    await rm(path.join(workspace, ".astro"), { recursive: true, force: true });
    await copyContentImages(contentRoot, staging);
    await writeFile(path.join(staging, ".nojekyll"), "");
    await install(staging, docs);
    installed = true;
  } finally {
    await rm(workspace, { recursive: true, force: true });
  }
}

try {
  await build();
} catch (error) {
  const raw = error instanceof Error ? error.message : String(error);
  const line = raw.split(/\r?\n/).find((value) => value.trim()) || "build failed";
  console.error(line);
  process.exitCode = 1;
}
