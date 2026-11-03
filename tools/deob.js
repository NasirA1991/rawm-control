// Deobfuscate the miracletek "hub" bundle by running its own string-table decoder.
const fs = require('fs');
const vm = require('vm');
const path = process.argv[2];
const out = process.argv[3];
let s = fs.readFileSync(path, 'utf8');

// Find end of function _0x1d36 {...}
function findFnEnd(src, name) {
  const i = src.indexOf('function ' + name);
  if (i < 0) throw new Error('no ' + name);
  let j = src.indexOf('{', i), depth = 0, inStr = null, esc = false;
  for (let k = j; k < src.length; k++) {
    const c = src[k];
    if (inStr) {
      if (esc) { esc = false; continue; }
      if (c === '\\') { esc = true; continue; }
      if (c === inStr) inStr = null;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') { inStr = c; continue; }
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) return k + 1; }
  }
  throw new Error('unbalanced');
}
const end = findFnEnd(s, '_0x1d36');
const prefix = s.slice(0, end);
const sandbox = { window: {}, document: {}, navigator: {}, console, setTimeout, clearTimeout };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(prefix + '\n;globalThis.__dec=_0x70bc;', sandbox);
const dec = sandbox.__dec;
if (typeof dec !== 'function') throw new Error('decoder not exposed');

// Discover aliases of the decoder.
const ids = new Set(['_0x70bc']);
let changed = true;
while (changed) {
  changed = false;
  for (const id of ids) {
    const re = new RegExp('([A-Za-z_$][\\w$]*)\\s*=\\s*' + id.replace(/[$]/g, '\\$') + '\\b', 'g');
    let m;
    while ((m = re.exec(s))) {
      if (!ids.has(m[1])) { ids.add(m[1]); changed = true; }
    }
  }
}
console.error('aliases:', [...ids].join(','));

let replaced = 0;
const esc = (str) => JSON.stringify(str);
for (const id of ids) {
  const re = new RegExp('(?<![\\w$.])' + id.replace(/[$]/g, '\\$') + '\\(\\s*(0x[0-9a-fA-F]+)\\s*\\)', 'g');
  s = s.replace(re, (m, hex) => {
    const v = dec(parseInt(hex, 16));
    if (v === undefined) { console.error('undef index', hex); return m; }
    replaced++;
    return esc(v);
  });
}
console.error('replaced', replaced);
fs.writeFileSync(out, s);
