// #N72 — LA HERENCIA REAL (v2 — orden de lectura): la plataforma PERSISTE los outputs
// grandes de hooks y solo inyecta un preview (~2KB) — PROTOCOLO+PERFIL suman ~20KB y se
// truncaban. Este hook inyecta la ORDEN OBLIGATORIA de leerlos: corta, siempre entra entera.
import { existsSync } from 'node:fs';
const files = [
  ['../el-universo/cerebro/PROTOCOLO_SESION.md', 'EL protocolo unico (inicio §1 · hito §3 · router §4 · TU CIERRE §6)'],
  ['../el-universo/especialistas/trader/PERFIL.md', 'tu PERFIL de rol (identidad, principios tecnicos, catalogo)']
];
console.log('⚓ ARRANQUE #N72 — HERENCIA OBLIGATORIA (aviso inyectado por el hook SessionStart):');
for (const [f, desc] of files) {
  if (existsSync(f)) {
    console.log(`- LEE COMPLETO ahora, ANTES de reportar el arranque: ${f} — ${desc}.`);
  } else {
    console.log(`- ⚠️ NO ENCUENTRO ${f} — avisale a Juan y al cerebro ANTES de trabajar.`);
  }
}
console.log('Estas lecturas SON parte del protocolo de inicio (§1), no opcionales — tu CLAUDE solo trae identidad y territorio. Confirma en tu reporte de arranque: "PROTOCOLO + PERFIL leidos ✓".');
