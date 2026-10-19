"use client";

import { useEffect, useState } from "react";
import { obtenerFicha, type Ficha, type Traza as TipoTraza } from "@/lib/api";
import { describir, ETIQUETA_RELACION, formatearCosto, hrefSeguro } from "@/lib/texto";
import { Traza } from "./Traza";

type Props = {
  tramiteId: number | null;
  traza: TipoTraza | null;
  onAbrirTramite: (id: number) => void;
};

export function Expediente({ tramiteId, traza, onAbrirTramite }: Props) {
  const [ficha, setFicha] = useState<Ficha | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tengo, setTengo] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (tramiteId === null) {
      setFicha(null);
      return;
    }
    const control = new AbortController();
    setError(null);
    setTengo(new Set());
    obtenerFicha(tramiteId, control.signal)
      .then(setFicha)
      .catch((e: Error) => {
        if (e.name !== "AbortError") setError("No pude abrir la ficha de este trámite. Vuelve a intentarlo.");
      });
    return () => control.abort();
  }, [tramiteId]);

  if (tramiteId === null && !traza) {
    return (
      <div className="expediente-vacio">
        <p>Cuando AMI encuentre tu trámite, aquí aparece su ficha: costo, requisitos y dónde hacerlo.</p>
        <p>Debajo verás cómo lo encontró, con los candidatos que comparó.</p>
      </div>
    );
  }

  const cargando = tramiteId !== null && !ficha && !error;
  const actual = ficha && ficha.id === tramiteId ? ficha : null;

  const alternarRequisito = (nombre: string) =>
    setTengo((previo) => {
      const siguiente = new Set(previo);
      if (siguiente.has(nombre)) siguiente.delete(nombre);
      else siguiente.add(nombre);
      return siguiente;
    });

  const ubicaciones = actual?.ubicaciones.map(describir).filter((x) => x !== null) ?? [];
  const enlaces = actual?.enlaces.map(describir).filter((x) => x !== null) ?? [];

  return (
    <div className="expediente-contenido">
      {cargando && <p className="cargando">Abriendo la ficha…</p>}
      {error && <p className="aviso-error">{error}</p>}

      {actual && (
        <article className="ficha">
          <header>
            {actual.entidad_nombre && <p className="ficha-entidad">{actual.entidad_nombre}</p>}
            <h2>{actual.nombre}</h2>
          </header>

          <div className="ficha-costo">
            {actual.costo_es_gratuito ? (
              <strong>Gratuito</strong>
            ) : actual.costo_monto !== null ? (
              <>
                <strong>{formatearCosto(actual.costo_monto, actual.costo_moneda)}</strong>
                {actual.costo_concepto && <span>{actual.costo_concepto}</span>}
              </>
            ) : (
              <span>El costo no figura en la ficha oficial.</span>
            )}
            {actual.canal && (
              <span className="ficha-canal">
                {actual.canal === "virtual" ? "Se hace en línea" : actual.canal === "ambos" ? "En línea o presencial" : "Presencial"}
              </span>
            )}
          </div>

          {actual.descripcion && <p className="ficha-descripcion">{actual.descripcion}</p>}

          {actual.requisitos.length > 0 && (
            <section>
              <h3>
                Requisitos{" "}
                <span className="contador">
                  {tengo.size} de {actual.requisitos.length} listos
                </span>
              </h3>
              <ul className="requisitos">
                {actual.requisitos.map((r) => (
                  <li key={r.nombre}>
                    <label>
                      <input type="checkbox" checked={tengo.has(r.nombre)} onChange={() => alternarRequisito(r.nombre)} />
                      <span>
                        {r.nombre}
                        {r.comentario && <small>{r.comentario}</small>}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {ubicaciones.length > 0 && (
            <section>
              <h3>Dónde se hace</h3>
              <ul className="lista-simple">
                {ubicaciones.slice(0, 4).map((u, i) => (
                  <li key={i}>{u.url ? <a href={u.url} target="_blank" rel="noopener noreferrer">{u.texto}</a> : u.texto}</li>
                ))}
              </ul>
            </section>
          )}

          {enlaces.length > 0 && (
            <section>
              <h3>Enlaces oficiales</h3>
              <ul className="lista-simple">
                {enlaces.slice(0, 4).map((e, i) => (
                  <li key={i}>{e.url ? <a href={e.url} target="_blank" rel="noopener noreferrer">{e.texto}</a> : e.texto}</li>
                ))}
              </ul>
            </section>
          )}

          {actual.relacionados.length > 0 && (
            <section>
              <h3>Trámites conectados</h3>
              <ul className="relacionados">
                {actual.relacionados.map((r) => (
                  <li key={r.id}>
                    <span>{ETIQUETA_RELACION[r.tipo] ?? r.tipo}</span>
                    <button type="button" onClick={() => onAbrirTramite(r.id)}>
                      {r.nombre}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <footer className="ficha-pie">
            {actual.last_updated && <>Ficha oficial actualizada el {new Date(actual.last_updated).toLocaleDateString("es-BO")}. </>}
            Confirma los datos con la entidad antes de ir.
            {hrefSeguro(actual.entidad_sitio_web) && (
              <>
                {" "}
                <a href={hrefSeguro(actual.entidad_sitio_web) ?? undefined} target="_blank" rel="noopener noreferrer">
                  Sitio de la entidad
                </a>
              </>
            )}
          </footer>
        </article>
      )}

      {traza && <Traza traza={traza} />}
    </div>
  );
}
