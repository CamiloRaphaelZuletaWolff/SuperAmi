/** El pipeline escribe para WhatsApp (*negrita*); en markdown eso sería cursiva. */
export function deWhatsappAMarkdown(texto: string): string {
  return texto.replace(/(^|[^*\w])\*(?!\s)([^*\n]+?)\*(?!\*)/g, "$1**$2**");
}

/** Los campos JSON del dataset (ubicaciones, enlaces, documentos) no tienen forma
 * fija entre fuentes: extraemos un texto legible y, si hay, una URL. */
export function describir(item: unknown): { texto: string; url: string | null } | null {
  if (item == null) return null;
  if (typeof item === "string") {
    const limpio = item.trim();
    if (!limpio) return null;
    return /^https?:\/\//.test(limpio) ? { texto: limpio, url: limpio } : { texto: limpio, url: null };
  }
  if (typeof item !== "object") return { texto: String(item), url: null };
  const o = item as Record<string, unknown>;
  const primero = (...claves: string[]) => {
    for (const c of claves) {
      const v = o[c];
      if (typeof v === "string" && v.trim()) return v.trim();
    }
    return null;
  };
  const url = primero("url", "enlace", "link", "href");
  const titulo = primero("nombre", "titulo", "title", "descripcion", "oficina");
  const direccion = primero("direccion", "address", "ubicacion");
  const partes = [titulo, direccion].filter(Boolean);
  const texto = partes.length ? partes.join(", ") : url;
  return texto ? { texto, url: url && /^https?:\/\//.test(url) ? url : null } : null;
}

export function formatearCosto(monto: number, moneda: string | null): string {
  const cifra = new Intl.NumberFormat("es-BO", { maximumFractionDigits: 2 }).format(monto);
  const m = (moneda ?? "").trim();
  if (!m || /^bs\.?$|boliviano/i.test(m)) return `Bs ${cifra}`;
  return `${cifra} ${m}`;
}

export const ETIQUETA_RELACION: Record<string, string> = {
  requisito_previo: "Antes necesitas",
  siguiente_paso: "Después sigue",
  alternativa: "Alternativa",
  mismo_evento: "También suele hacerse",
};
