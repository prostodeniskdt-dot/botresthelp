import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, "..");
const SOURCE = path.join(ROOT, "data", "ttk_source.txt");
const OUT = path.join(ROOT, "data", "recipes.json");

const TITLE_RE = /^(.+?)\s+(Подача:?|Приготовление:?|Метод:?)\s*$/;

const LABEL_RE =
  /^\s*(Бокал|Метод|Лед|Украшение|Пребэтч|Выход)\s*:\s*(.*)$/is;

const KEY_MAP = {
  бокал: "glass",
  метод: "method",
  лед: "ice",
  украшение: "garnish",
  пребэтч: "prebatch",
  выход: "yield",
};

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

function ingredientJoin(parts) {
  return parts
    .map((p) => p.trim())
    .filter(Boolean)
    .join("  ");
}

function formatPlainIngredient(s) {
  s = s.trim();
  const m = s.match(/^([\d.,]+)\s+(\S+)\s+(.+)$/);
  if (m) return `${m[1]}  ${m[2]}  ${m[3].trim()}`;
  return s;
}

function startsAmount(s) {
  return /^[\d.,]+\s*/.test(s.trim());
}

function setMeta(meta, key, value) {
  value = (value || "").trim();
  if (!value) return;
  if (meta[key]) return;
  meta[key] = value;
}

function labelMatch(part) {
  const m = part.trim().match(LABEL_RE);
  if (!m) return [null, part];
  const ru = m[1].toLowerCase();
  const key = KEY_MAP[ru];
  if (!key) return [null, part];
  return [key, (m[2] || "").trim()];
}

function parsePlainLine(line, ingredients, notes, meta) {
  let [key, rest] = labelMatch(line);
  if (key) {
    setMeta(meta, key, rest);
    return;
  }
  const low = line.toLowerCase().trim();
  if (low === "подача:" || low === "приготовление:") return;
  if (startsAmount(line)) {
    ingredients.push(formatPlainIngredient(line));
    return;
  }
  notes.push(line.trim());
}

function parseTabLine(line, ingredients, notes, meta) {
  const parts = line.split("\t").map((p) => p.trim());
  let i = 0;
  while (i < parts.length) {
    const p = parts[i];
    if (!p) {
      i += 1;
      continue;
    }

    let [key, rest] = labelMatch(p);
    if (key) {
      let val = rest;
      if (!val && i + 1 < parts.length) {
        const [nk] = labelMatch(parts[i + 1]);
        if (!nk) {
          val = parts[i + 1];
          i += 1;
        }
      }
      setMeta(meta, key, val);
      i += 1;
      continue;
    }

    if (!startsAmount(p)) {
      let j = i + 1;
      while (j < parts.length) {
        if (labelMatch(parts[j])[0]) break;
        if (startsAmount(parts[j])) break;
        j += 1;
      }
      const chunk = parts.slice(i, j);
      const lead = chunk.join(" ").trim();
      if (lead) notes.push(lead);
      i = j;
      continue;
    }

    const segStart = i;
    i += 1;
    while (i < parts.length) {
      const [nk] = labelMatch(parts[i]);
      if (nk) break;
      if (startsAmount(parts[i]) && i > segStart) break;
      i += 1;
    }
    const seg = parts.slice(segStart, i);
    if (seg.length) ingredients.push(ingredientJoin(seg));
  }
}

function parseTtkBody(text) {
  text = text.replace(/\r\n/g, "\n").trim();
  const ingredients = [];
  const notes = [];
  const meta = {
    method: null,
    glass: null,
    ice: null,
    garnish: null,
    prebatch: null,
    yield: null,
  };

  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    if (!line) continue;
    if (line.includes("\t")) parseTabLine(line, ingredients, notes, meta);
    else parsePlainLine(line, ingredients, notes, meta);
  }

  const out = { ingredients, notes };
  for (const [k, v] of Object.entries(meta)) {
    if (v) out[k] = v;
  }
  return out;
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
    const name = cleanName(m[1]);
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
  return Object.keys(recipes)
    .sort((a, b) => a.localeCompare(b, "ru"))
    .map((name) => ({ name, ...parseTtkBody(recipes[name]) }));
}

const text = fs.readFileSync(SOURCE, "utf8");
const recipes = parseTtk(text);
fs.writeFileSync(OUT, JSON.stringify({ recipes }, null, 2), "utf8");
console.log(`Записано ${recipes.length} техкарт в ${OUT}`);
