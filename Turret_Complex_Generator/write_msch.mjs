import { existsSync, readFileSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { spawnSync } from "child_process";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const args = process.argv.slice(2);
if (args.length < 2) {
    console.error("Usage : node write_msch.mjs <tiles.json> <sortie.msch>");
    process.exit(1);
}

const tilesPath = path.resolve(args[0]);
const mschPath  = path.resolve(args[1]);

if (!existsSync(tilesPath)) {
    console.error("tiles.json introuvable : " + tilesPath);
    process.exit(1);
}

const cliPath = path.join(
    process.env.APPDATA || "/usr/lib",
    "npm", "node_modules", "msch-generate", "build", "cli.js"
);

if (!existsSync(cliPath)) {
    console.error("cli.js introuvable : " + cliPath);
    process.exit(1);
}

// msch build --output <mschPath> --no-show <tilesPath>
const result = spawnSync(process.execPath, [
    cliPath,
    "build",
    "--output", mschPath,
    "--no-show",
    tilesPath
], { encoding: "utf-8" });

const out = ((result.stdout || "") + (result.stderr || "")).trim();
if (out) console.log(out);

if (result.status !== 0) {
    console.error("Erreur génération .msch (code " + result.status + ")");
    process.exit(1);
}

if (!existsSync(mschPath)) {
    console.error("Fichier .msch non créé : " + mschPath);
    process.exit(1);
}

const size = readFileSync(mschPath).length;
console.log("OK msch écrit : " + mschPath + " (" + size + " octets)");
