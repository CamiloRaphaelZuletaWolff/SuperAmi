import type { Veredicto } from "@/lib/api";

const TEXTO: Record<Veredicto, { titulo: string; detalle: string }> = {
  claro: { titulo: "Encontrado", detalle: "coincidencia clara" },
  ambiguo: { titulo: "Por aclarar", detalle: "dos trámites parecidos" },
  lejano: { titulo: "Consulta en vivo", detalle: "fuera de la base" },
  vacio: { titulo: "Sin resultado", detalle: "nada parecido" },
};

const FECHA = new Intl.DateTimeFormat("es-BO", { day: "2-digit", month: "short", year: "numeric" });

/** El veredicto del confidence gate, estampado como un sello de ventanilla. */
export function Sello({ veredicto, onClick, activo }: { veredicto: Veredicto; onClick?: () => void; activo?: boolean }) {
  const { titulo, detalle } = TEXTO[veredicto];
  return (
    <button
      type="button"
      className="sello"
      data-veredicto={veredicto}
      data-activo={activo || undefined}
      onClick={onClick}
      title="Ver cómo se encontró este trámite"
    >
      <span className="sello-titulo">{titulo}</span>
      <span className="sello-detalle">{detalle}</span>
      <span className="sello-fecha">{FECHA.format(new Date()).replace(".", "")}</span>
    </button>
  );
}
