"use client";

import { useEffect, useRef } from "react";
import type { Stats } from "@/lib/api";

export function ComoFunciona({ abierto, onCerrar, stats }: { abierto: boolean; onCerrar: () => void; stats: Stats | null }) {
  const dialogo = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = dialogo.current;
    if (!d) return;
    if (abierto && !d.open) d.showModal();
    if (!abierto && d.open) d.close();
  }, [abierto]);

  const total = stats ? stats.tramites.toLocaleString("es-BO") : "1.814";

  return (
    <dialog ref={dialogo} className="como-funciona" onClose={onCerrar} aria-labelledby="como-funciona-titulo">
      <h2 id="como-funciona-titulo">Cómo responde AMI</h2>
      <p>
        AMI no inventa trámites: cada respuesta sale de la ficha oficial de uno solo. Para elegirla, tu mensaje pasa por
        estos pasos.
      </p>
      <ol>
        <li>
          <strong>Entiende de qué hablas.</strong> Un modelo liviano deduce la categoría, la entidad o el momento de vida
          (abrir un negocio, comprar una casa) para acotar la búsqueda.
        </li>
        <li>
          <strong>Busca por significado.</strong> Tu pregunta se convierte en un vector y se compara con {total} trámites
          guardados en Postgres con pgvector.
        </li>
        <li>
          <strong>Decide si está seguro.</strong> Una regla fija, sin IA, mira qué tan cerca está el mejor candidato y
          cuánto se separa del segundo. Si duda, te pregunta cuál de los dos buscas. Ese veredicto es el sello que ves en
          cada respuesta.
        </li>
        <li>
          <strong>Redacta con la ficha.</strong> El modelo grande escribe la respuesta usando solo los datos oficiales del
          trámite elegido, y suma los trámites que van antes o después.
        </li>
        <li>
          <strong>Si no está en la base, consulta en vivo.</strong> Lee la página oficial del trámite más cercano antes de
          decirte que no lo encontró.
        </li>
      </ol>
      <p className="como-funciona-pie">Toca cualquier sello para ver los candidatos que comparó y sus distancias.</p>
      <form method="dialog">
        <button type="submit">Entendido</button>
      </form>
    </dialog>
  );
}
