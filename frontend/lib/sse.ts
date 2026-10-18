export type EventoSSE = { evento: string; data: unknown };

/**
 * Parser incremental de Server-Sent Events. /chat es un POST, así que no sirve
 * EventSource: leemos el body con fetch y cortamos por bloques "\n\n".
 * Devuelve los eventos completos y el resto sin terminar para el próximo chunk.
 */
export function parsearBloques(buffer: string): { eventos: EventoSSE[]; resto: string } {
  const normalizado = buffer.replace(/\r\n/g, "\n");
  const bloques = normalizado.split("\n\n");
  const resto = bloques.pop() ?? "";
  const eventos: EventoSSE[] = [];
  for (const bloque of bloques) {
    let evento = "message";
    const datos: string[] = [];
    for (const linea of bloque.split("\n")) {
      if (linea.startsWith("event:")) evento = linea.slice(6).trim();
      else if (linea.startsWith("data:")) datos.push(linea.slice(5).trimStart());
    }
    if (datos.length === 0) continue;
    try {
      eventos.push({ evento, data: JSON.parse(datos.join("\n")) });
    } catch {
      // bloque corrupto: se descarta en vez de cortar la conversación
    }
  }
  return { eventos, resto };
}
