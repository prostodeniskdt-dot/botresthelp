import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, "..");
const SOURCE = path.join(ROOT, "data", "ttk_source.txt");
const OUT = path.join(ROOT, "data", "recipes.json");

const TITLE_RE = /^(.+?)\s+(Подача:?|Приготовление:?|Метод:?)\s*$/;

function skipBodyLine(line) {
  const s = line.trim();
  if (!s) return true;
  if (/^--\s*\d+\s+of\s+\d+\s*--$/.test(s)) return true;
  if (s === "[") return true;
  if (s === "Е") return true;
  return false;
}

function cleanName(raw) {
  return raw
    .trim()
    .replace(/^[ЕЕ]\s+/, "")
    .trim();
}

function parseTtk(text) {
  text = text.replace(/--\s*\d+\s+of\s+\d+\s*--/g, "");
  const lines = text.split("\n");
  const recipes = {};
  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();
    const m = line.match(TITLE_RE);
    if (!m) {
      i++;
      continue;
    }
    if (m[2].startsWith("Метод") && /^\d/.test(line.trim())) {
      i++;
      continue;
    }
    let name = cleanName(m[1]);
    if (!name) {
      i++;
      continue;
    }
    i++;
    const body = [];
    while (i < lines.length) {
      const nxt = lines[i].trim();
      if (TITLE_RE.test(nxt)) {
        const parts = nxt.match(TITLE_RE);
        if (parts && parts[2].startsWith("Метод") && /^\d/.test(nxt)) {
          body.push(lines[i]);
          i++;
          continue;
        }
        break;
      }
      if (skipBodyLine(lines[i])) {
        i++;
        continue;
      }
      body.push(lines[i]);
      i++;
    }
    let textBody = body.join("\n").trim();
    textBody = textBody.replace(/\r\n/g, "\n");
    if (!textBody) continue;
    if (recipes[name] && textBody.length <= recipes[name].length) continue;
    recipes[name] = textBody;
  }
  const items = Object.keys(recipes)
    .sort((a, b) => a.localeCompare(b, "ru"))
    .map((name) => ({ name, text: recipes[name] }));
  return items;
}

const text = fs.readFileSync(SOURCE, "utf8");
const recipes = parseTtk(text);
fs.writeFileSync(OUT, JSON.stringify({ recipes }, null, 2), "utf8");
console.log(`Записано ${recipes.length} техкарт в ${OUT}`);
