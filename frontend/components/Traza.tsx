import type { Traza as TipoTraza } from "@/lib/api";

const ESCALA = 0.8; // distancia coseno que llena la barra completa

const EXPLICACION: Record<TipoTraza["veredicto"], string> = {
  claro: "El primer candidato está cerca de la consulta y bien separado del segundo, así que AMI responde con ese trámite.",
  ambiguo: "Los dos primeros candidatos están casi empatados. En vez de adivinar, AMI pregunta cuál de los dos buscas.",
  lejano: "Ningún trámite de la base queda bajo el umbral. AMI intenta leer la página oficial en vivo antes de rendirse.",
  vacio: "La búsqueda no devolvió candidatos dentro del alcance (impuestos, empresas y trámites municipales).",
};

const NOMBRE_FILTRO: Record<string, string> = {
  categoria_slug: "Categoría",
  entidad_slug: "Entidad",
  evento_nombre: "Momento de vida",
};

export function Traza({ traza }: { traza: TipoTraza }) {
  const { candidatos, umbrales, filtros, veredicto } = traza;
  const gap = candidatos.length > 1 ? candidatos[1].distancia - candidatos[0].distancia : null;
  const filtrosUsados = Object.entries(filtros);

  return (
    <section className="traza" aria-label="Cómo se encontró el trámite">
      <h3>Cómo lo encontré</h3>
      <p className="traza-explicacion">{EXPLICACION[veredicto]}</p>

      {filtrosUsados.length > 0 && (
        <dl className="traza-filtros">
          {filtrosUsados.map(([clave, valor]) => (
            <div key={clave}>
              <dt>{NOMBRE_FILTRO[clave] ?? clave}</dt>
              <dd>{valor}</dd>
            </div>
          ))}
        </dl>
      )}

      {candidatos.length > 0 && (
        <>
          <ol className="candidatos">
            {candidatos.map((c, i) => (
              <li key={c.id} data-primero={i === 0 || undefined}>
                <div className="candidato-nombre">
                  <span>{c.nombre}</span>
                  {c.entidad_nombre && <small>{c.entidad_nombre}</small>}
                </div>
                <div
                  className="barra"
                  role="img"
                  aria-label={`Distancia ${c.distancia.toFixed(3)}`}
                  style={{ ["--umbral" as string]: `${(umbrales.distancia_max / ESCALA) * 100}%` }}
                >
                  <span style={{ width: `${Math.min(c.distancia / ESCALA, 1) * 100}%` }} />
                </div>
                <span className="candidato-distancia">{c.distancia.toFixed(3)}</span>
              </li>
            ))}
          </ol>
          <p className="traza-nota">
            Distancia coseno entre tu consulta y cada trámite: más corta es más parecida. La marca vertical es el
            umbral de {umbrales.distancia_max}
            {gap !== null && (
              <>
                {"; "}la separación entre los dos primeros es {gap.toFixed(3)} y hace falta {umbrales.gap} para
                considerarla clara
              </>
            )}
            .
          </p>
        </>
      )}
    </section>
  );
}
