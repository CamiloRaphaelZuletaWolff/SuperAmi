"use client";

import { useEffect, useState } from "react";
import { salud } from "@/lib/api";

/** El backend vive en el plan gratuito de Render y se duerme tras 15 min sin
 * tráfico. Si /health no contesta rápido, avisamos en vez de parecer roto. */
export function Despertador({ onListo }: { onListo: () => void }) {
  const [estado, setEstado] = useState<"probando" | "despertando" | "listo">("probando");

  useEffect(() => {
    let vivo = true;
    const aviso = setTimeout(() => vivo && setEstado((e) => (e === "probando" ? "despertando" : e)), 2000);

    (async () => {
      const inicio = Date.now();
      while (vivo && Date.now() - inicio < 120_000) {
        const control = new AbortController();
        const corte = setTimeout(() => control.abort(), 15_000);
        const ok = await salud(control.signal);
        clearTimeout(corte);
        if (ok) {
          if (vivo) {
            setEstado("listo");
            onListo();
          }
          return;
        }
        await new Promise((r) => setTimeout(r, 3000));
      }
    })();

    return () => {
      vivo = false;
      clearTimeout(aviso);
    };
  }, [onListo]);

  if (estado !== "despertando") return null;
  return (
    <div className="despertador" role="status">
      <span className="pulso" aria-hidden />
      Despertando el servidor. Este demo corre en un plan gratuito que se duerme sin visitas; tarda cerca de un minuto
      la primera vez.
    </div>
  );
}
