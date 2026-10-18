"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { conversar, ErrorApi, obtenerStats, type Stats, type Traza } from "@/lib/api";
import { deWhatsappAMarkdown } from "@/lib/texto";
import { ComoFunciona } from "./ComoFunciona";
import { Despertador } from "./Despertador";
import { Expediente } from "./Expediente";
import { Sello } from "./Sello";

type Mensaje = {
  id: number;
  rol: "persona" | "ami";
  texto: string;
  tipo: "respuesta" | "aclaracion" | "error";
  pendiente: boolean;
  traza: Traza | null;
  tramiteId: number | null;
};

type Seleccion = { mensajeId: number | null; tramiteId: number | null; traza: Traza | null };

const EJEMPLOS = [
  "¿Cuánto cuesta el certificado catastral en La Paz?",
  "Quiero abrir una empresa unipersonal",
  "¿Cómo pago el impuesto de mi auto?",
  "Necesito licencia de funcionamiento para una tienda",
];

const REPO = "https://github.com/CamiloRaphaelZuletaWolff/SuperAmi";
const SIN_SELECCION: Seleccion = { mensajeId: null, tramiteId: null, traza: null };

export function Asistente() {
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [borrador, setBorrador] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [conversacion, setConversacion] = useState<string | null>(null);
  const [seleccion, setSeleccion] = useState<Seleccion>(SIN_SELECCION);
  const [panelAbierto, setPanelAbierto] = useState(false);
  const [stats, setStats] = useState<Stats | null>(null);
  const [comoFunciona, setComoFunciona] = useState(false);
  const siguienteId = useRef(1);
  const finDeLista = useRef<HTMLDivElement>(null);
  const entrada = useRef<HTMLTextAreaElement>(null);

  const alDespertar = useCallback(() => {
    obtenerStats().then(setStats).catch(() => setStats(null));
  }, []);

  useEffect(() => {
    finDeLista.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [mensajes]);

  const actualizar = (id: number, cambios: Partial<Mensaje> | ((m: Mensaje) => Partial<Mensaje>)) =>
    setMensajes((lista) =>
      lista.map((m) => (m.id === id ? { ...m, ...(typeof cambios === "function" ? cambios(m) : cambios) } : m)),
    );

  async function enviar(texto: string) {
    const limpio = texto.trim();
    if (!limpio || enviando) return;
    const idPersona = siguienteId.current++;
    const idAmi = siguienteId.current++;
    setMensajes((lista) => [
      ...lista,
      { id: idPersona, rol: "persona", texto: limpio, tipo: "respuesta", pendiente: false, traza: null, tramiteId: null },
      { id: idAmi, rol: "ami", texto: "", tipo: "respuesta", pendiente: true, traza: null, tramiteId: null },
    ]);
    setBorrador("");
    setEnviando(true);

    let traza: Traza | null = null;
    try {
      for await (const { evento, data } of conversar(limpio, conversacion)) {
        const d = data as Record<string, unknown>;
        if (typeof d.conversation_id === "string") setConversacion(d.conversation_id);

        if (evento === "trace") {
          traza = d as unknown as Traza;
          actualizar(idAmi, { traza });
        } else if (evento === "answer" && typeof d.delta === "string") {
          const delta = d.delta;
          actualizar(idAmi, (m) => ({ texto: m.texto + delta }));
        } else if (evento === "answer" && d.done) {
          const ids = (d.tramite_ids as number[]) ?? [];
          const tramiteId = ids[0] ?? null;
          actualizar(idAmi, { pendiente: false, tramiteId });
          if (tramiteId !== null || traza) setSeleccion({ mensajeId: idAmi, tramiteId, traza });
        } else if (evento === "clarification") {
          actualizar(idAmi, { texto: String(d.text ?? ""), tipo: "aclaracion", pendiente: false });
          if (traza) setSeleccion({ mensajeId: idAmi, tramiteId: null, traza });
        } else if (evento === "error") {
          actualizar(idAmi, { texto: String(d.message ?? ""), tipo: "error", pendiente: false });
        }
      }
    } catch (e) {
      const texto =
        e instanceof ErrorApi
          ? e.message
          : "No pude conectar con el servidor. Revisa tu conexión y envía la pregunta de nuevo.";
      actualizar(idAmi, { texto, tipo: "error", pendiente: false });
    } finally {
      actualizar(idAmi, { pendiente: false });
      setEnviando(false);
      entrada.current?.focus();
    }
  }

  function nuevaConsulta() {
    setMensajes([]);
    setConversacion(null);
    setSeleccion(SIN_SELECCION);
    setPanelAbierto(false);
    entrada.current?.focus();
  }

  const hayExpediente = seleccion.tramiteId !== null || seleccion.traza !== null;

  return (
    <div className="app">
      <header className="cabecera">
        <div className="aguayo" aria-hidden />
        <div className="cabecera-fila">
          <button type="button" className="marca" onClick={nuevaConsulta} aria-label="AMI, empezar una consulta nueva">
            <span className="marca-nombre">AMI</span>
            <span className="marca-lema">Asistente de trámites de Bolivia</span>
          </button>
          <nav className="cabecera-nav">
            <button type="button" onClick={() => setComoFunciona(true)}>
              Cómo funciona
            </button>
            <a href={REPO} target="_blank" rel="noreferrer">
              Código
            </a>
          </nav>
        </div>
      </header>

      <Despertador onListo={alDespertar} />

      <main className="mesa">
        <section className="conversacion" aria-label="Conversación con AMI">
          <div className="mensajes" aria-live="polite">
            {mensajes.length === 0 ? (
              <div className="bienvenida">
                <h1>¿Qué trámite necesitas hacer?</h1>
                <p>
                  Te digo los requisitos, cuánto cuesta y dónde hacerlo. Por ahora conozco impuestos, empresas y
                  trámites municipales, catastro incluido.
                </p>
                {stats && (
                  <p className="bienvenida-cifras">
                    Busco entre {stats.en_dominio.toLocaleString("es-BO")} trámites oficiales de{" "}
                    {stats.entidades.toLocaleString("es-BO")} entidades públicas, conectados por{" "}
                    {stats.relaciones.toLocaleString("es-BO")} relaciones.
                  </p>
                )}
                <div className="ejemplos">
                  {EJEMPLOS.map((e) => (
                    <button key={e} type="button" onClick={() => enviar(e)} disabled={enviando}>
                      {e}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              mensajes.map((m) => (
                <article key={m.id} className="mensaje" data-rol={m.rol} data-tipo={m.tipo}>
                  {m.rol === "ami" && m.traza && (
                    <Sello
                      veredicto={m.traza.veredicto}
                      activo={seleccion.mensajeId === m.id}
                      onClick={() => {
                        setSeleccion({ mensajeId: m.id, tramiteId: m.tramiteId, traza: m.traza });
                        setPanelAbierto(true);
                      }}
                    />
                  )}
                  {m.pendiente && !m.texto ? (
                    <p className="escribiendo">{m.traza ? "Redactando con la ficha oficial…" : "Buscando entre los trámites…"}</p>
                  ) : m.rol === "ami" ? (
                    <div className="markdown">
                      <ReactMarkdown
                        components={{
                          a: ({ href, children }) => (
                            <a href={href} target="_blank" rel="noreferrer">
                              {children}
                            </a>
                          ),
                        }}
                      >
                        {deWhatsappAMarkdown(m.texto)}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <p>{m.texto}</p>
                  )}
                </article>
              ))
            )}
            <div ref={finDeLista} />
          </div>

          <form
            className="ventanilla"
            onSubmit={(e) => {
              e.preventDefault();
              enviar(borrador);
            }}
          >
            <label htmlFor="pregunta" className="solo-lectores">
              Tu pregunta
            </label>
            <textarea
              id="pregunta"
              ref={entrada}
              value={borrador}
              maxLength={1000}
              rows={1}
              placeholder="Escribe tu trámite con tus palabras, por ejemplo: papeles para vender mi casa"
              onChange={(e) => setBorrador(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  enviar(borrador);
                }
              }}
            />
            <button type="submit" disabled={enviando || !borrador.trim()}>
              {enviando ? "Buscando" : "Preguntar"}
            </button>
          </form>
        </section>

        <aside className="expediente" data-abierto={panelAbierto || undefined} aria-label="Expediente del trámite">
          <div className="expediente-cabecera">
            <h2>Expediente</h2>
            <button type="button" className="cerrar" onClick={() => setPanelAbierto(false)}>
              Volver al chat
            </button>
          </div>
          <Expediente
            tramiteId={seleccion.tramiteId}
            traza={seleccion.traza}
            onAbrirTramite={(id) => setSeleccion({ mensajeId: null, tramiteId: id, traza: null })}
          />
        </aside>

        {hayExpediente && !panelAbierto && (
          <button type="button" className="abrir-expediente" onClick={() => setPanelAbierto(true)}>
            Ver la ficha del trámite
          </button>
        )}
      </main>

      <footer className="pie">
        Información orientativa basada en el catálogo abierto de trámites de Bolivia (datos CC0). Confirma siempre con la
        entidad. También respondo por WhatsApp.
      </footer>

      <ComoFunciona abierto={comoFunciona} onCerrar={() => setComoFunciona(false)} stats={stats} />
    </div>
  );
}
