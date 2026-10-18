import { parsearBloques, type EventoSSE } from "./sse";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type Veredicto = "claro" | "ambiguo" | "lejano" | "vacio";

export type Candidato = {
  id: number;
  nombre: string;
  entidad_nombre: string | null;
  distancia: number;
};

export type Traza = {
  veredicto: Veredicto;
  umbrales: { gap: number; distancia_max: number };
  filtros: Record<string, string>;
  candidatos: Candidato[];
};

export type Relacionado = { id: number; tipo: string; nombre: string; entidad_nombre: string | null };

export type Ficha = {
  id: number;
  nombre: string;
  descripcion: string | null;
  resultado: string | null;
  canal: string | null;
  digitalizado: boolean;
  costo_monto: number | null;
  costo_moneda: string | null;
  costo_concepto: string | null;
  costo_es_gratuito: boolean;
  requisitos: { nombre: string; comentario: string | null }[];
  documentos: unknown[];
  ubicaciones: unknown[];
  modalidades: unknown[];
  enlaces: unknown[];
  last_updated: string | null;
  fuente: string;
  entidad_nombre: string | null;
  entidad_sigla: string | null;
  entidad_sitio_web: string | null;
  relacionados: Relacionado[];
};

export type Stats = { tramites: number; en_dominio: number; entidades: number; relaciones: number };

export class ErrorApi extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function errorDe(respuesta: Response): Promise<ErrorApi> {
  let detalle = `El servidor respondió ${respuesta.status}.`;
  try {
    const cuerpo = await respuesta.json();
    if (typeof cuerpo?.detail === "string") detalle = cuerpo.detail;
  } catch {
    // cuerpo no-JSON: queda el mensaje genérico
  }
  return new ErrorApi(detalle, respuesta.status);
}

/** Envía un mensaje y va entregando los eventos SSE a medida que llegan. */
export async function* conversar(
  mensaje: string,
  conversationId: string | null,
  signal?: AbortSignal,
): AsyncGenerator<EventoSSE> {
  const respuesta = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mensaje, conversation_id: conversationId, traza: true }),
    signal,
  });
  if (!respuesta.ok || !respuesta.body) throw await errorDe(respuesta);

  const lector = respuesta.body.getReader();
  const decodificador = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await lector.read();
    if (done) break;
    buffer += decodificador.decode(value, { stream: true });
    const { eventos, resto } = parsearBloques(buffer);
    buffer = resto;
    yield* eventos;
  }
  const { eventos } = parsearBloques(buffer + "\n\n");
  yield* eventos;
}

export async function obtenerFicha(id: number, signal?: AbortSignal): Promise<Ficha> {
  const respuesta = await fetch(`${API_URL}/tramites/${id}`, { signal });
  if (!respuesta.ok) throw await errorDe(respuesta);
  return respuesta.json();
}

export async function obtenerStats(signal?: AbortSignal): Promise<Stats> {
  const respuesta = await fetch(`${API_URL}/stats`, { signal });
  if (!respuesta.ok) throw await errorDe(respuesta);
  return respuesta.json();
}

export async function salud(signal?: AbortSignal): Promise<boolean> {
  try {
    const respuesta = await fetch(`${API_URL}/health`, { signal, cache: "no-store" });
    return respuesta.ok;
  } catch {
    return false;
  }
}
