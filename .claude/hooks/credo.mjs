// #N71 — inyecta el CREDO en cada turno (UserPromptSubmit).
import { readFileSync } from 'node:fs';
try {
  process.stdout.write(readFileSync('CREDO.md', 'utf8'));
} catch (e) {
  console.log(`[hook credo] NO PUDE LEER CREDO.md: ${e.message} — releelo manualmente AHORA (#N71).`);
}
