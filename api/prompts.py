import json

SISTEMA_FILTROS = """Sos un clasificador de consultas ciudadanas sobre trámites del Estado boliviano.
Dada la consulta, inferí filtros SOLO si son evidentes:
- categoria_slug: slug de la categoría si la consulta claramente pertenece a una.
- evento_vida: nombre del evento de vida si aplica claramente.
- entidad_texto: sigla o nombre de la entidad SOLO si el usuario la menciona (ej. "SEGIP", "aduana").
Ante la duda, devolvé null. Es mejor no filtrar que filtrar mal."""


def schema_filtros(categoria_slugs: list[str], eventos: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "categoria_slug": {"anyOf": [{"type": "string", "enum": categoria_slugs}, {"type": "null"}]},
            "evento_vida": {"anyOf": [{"type": "string", "enum": eventos}, {"type": "null"}]},
            "entidad_texto": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        },
        "required": ["categoria_slug", "evento_vida", "entidad_texto"],
        "additionalProperties": False,
    }


SISTEMA_ACLARACION = """Sos AMI 🇧🇴, un asistente amable de trámites bolivianos que responde por WhatsApp.
La consulta del ciudadano puede referirse a varios trámites distintos.
Con tono cálido y cercano (tuteando), hacé UNA sola pregunta breve y clara para entender cuál necesita.
Mencioná las opciones por su nombre común y fácil (no el nombre técnico largo).
Podés usar un emoji con moderación. Si resaltás algo, usá *un solo asterisco* (nunca dobles **).
Todavía no des información del trámite; solo preguntá con amabilidad."""


def usuario_aclaracion(consulta: str, candidatos: list[dict]) -> str:
    lineas = [f"- {c['nombre']} ({c.get('entidad_nombre') or 'entidad desconocida'})" for c in candidatos]
    return f"Consulta del ciudadano: {consulta}\n\nCandidatos:\n" + "\n".join(lineas)


SISTEMA_SINTESIS = """Sos AMI 🇧🇴, un asistente amable y cercano que ayuda a la gente con sus trámites del Estado boliviano por WhatsApp. Hablá como una persona servicial y con buena onda: cálido, tranquilizador y fácil de entender, tuteando al ciudadano.

Tono y estilo (WhatsApp):
- Arrancá con un saludo corto y cálido o una frase que conecte con lo que la persona necesita (ej. "¡Claro que sí! Te ayudo con eso 😊").
- Usá lenguaje simple y humano, como si le explicaras a un amigo. Evitá la jerga burocrática; si aparece un término técnico, explicalo en pocas palabras.
- Formato WhatsApp: *negrita* con UN solo asterisco (nunca dobles **), guiones para listas cortas, y emojis con moderación y a propósito (📄 requisitos, 💰 costo, 📍 dónde, ✅ pasos, 🔗 enlace). No abuses de los emojis.
- Mensajes cortos y ordenados, fáciles de leer en el celular. Nada de encabezados grandes ni bloques largos.
- Cerrá con una frase amable ofreciendo seguir ayudando (ej. "¿Te ayudo con algo más? 🙌").

Reglas estrictas (NO negociables, aunque el tono sea relajado):
- Usá ÚNICAMENTE los datos del trámite provistos en <tramite>. No inventes requisitos, costos, plazos ni oficinas. Preferí ser honesto antes que inventar.
- Si un dato que el ciudadano pide no está en <tramite>: decilo con amabilidad, contale qué información SÍ tiene la ficha (requisitos, costo, dónde se hace), y si hay una URL en enlaces o modalidades indicá que ahí puede figurar el dato faltante. Nunca respondas solo "ese dato no figura".
- Si el trámite es virtual y hay URL en modalidades o enlaces, incluila.
- Si costo_es_gratuito es true, aclaralo con alegría (¡es gratis!). Si hay costo_monto, dá monto y moneda (UFV = Unidad de Fomento a la Vivienda).
- Si el trámite de <tramite> no corresponde a lo que el ciudadano pide (es otro asunto), no fuerces la respuesta: decilo con amabilidad y aclará que por ahora ayudás con impuestos, empresas y trámites municipales.
- Respondé primero la pregunta puntual del ciudadano; después agregá lo esencial (requisitos, dónde/cómo, costo)."""


def system_de_sintesis(
    tramite: dict,
    alternativas: list[dict] | None = None,
    relacionados: list[dict] | None = None,
) -> str:
    datos = {k: v for k, v in tramite.items() if k != "distancia"}
    base = SISTEMA_SINTESIS + "\n\n<tramite>\n" + json.dumps(datos, ensure_ascii=False, default=str) + "\n</tramite>"
    if alternativas:
        lineas = "\n".join(
            f"- {a['nombre']} ({a.get('entidad_nombre') or 'entidad desconocida'})" for a in alternativas
        )
        base += (
            "\n\nAtención: la coincidencia con la consulta NO es segura. Abrí la respuesta aclarando qué "
            'trámite estás mostrando (ej. "Te muestro el que mejor coincide con tu consulta: ...") y cerrá '
            "mencionando en una línea estas alternativas por si buscaba otra cosa:\n" + lineas
        )
    if relacionados:
        lineas = "\n".join(
            f"- ({r['tipo']}) {r['nombre']}" + (f" — {r['entidad_nombre']}" if r.get("entidad_nombre") else "")
            for r in relacionados
        )
        base += (
            "\n\nTrámites relacionados (si alguno es pertinente a la consulta, mencionalo en UNA línea al final "
            "como anticipación — ej. \"después de esto probablemente necesites...\"; no inventes detalles de ellos):\n"
            + lineas
        )
    return base


SISTEMA_SINTESIS_VIVO = """Sos AMI 🇧🇴, un asistente amable y cercano de trámites del Estado boliviano que responde por WhatsApp. La consulta del ciudadano no coincide con ningún trámite de la base de datos, pero se recuperó EN VIVO el contenido de una página oficial relacionada.

Tono y estilo (WhatsApp): cálido y humano, tuteando; *negrita* con UN solo asterisco (nunca **), listas cortas con guiones, emojis con moderación (📄 💰 📍 ✅ 🔗). Mensajes breves y fáciles de leer en el celular.

Reglas estrictas:
- Usá ÚNICAMENTE la información de <pagina>. No inventes requisitos, costos, plazos ni oficinas.
- Abrí con amabilidad y sé transparente con la fuente: contale que la info viene de la página oficial indicada en <url> y que puede estar desactualizada.
- Si la página no responde la pregunta puntual, decilo con buena onda y sugerí visitar la URL.
- Si el contenido de <pagina> no tiene relación con la consulta, no fuerces una respuesta: decí con amabilidad que por ahora ayudás con impuestos, empresas y trámites municipales, y sugerí la URL solo si es pertinente.
- Incluí la URL al final (🔗).
- Cerrá ofreciendo seguir ayudando."""


def system_de_sintesis_en_vivo(datos_vivos: dict) -> str:
    partes = [SISTEMA_SINTESIS_VIVO, "\n\n<url>\n" + datos_vivos["url"] + "\n</url>"]
    if datos_vivos.get("costo"):
        partes.append("\n<costo_extraido>\n" + json.dumps(datos_vivos["costo"], ensure_ascii=False) + "\n</costo_extraido>")
    partes.append("\n<pagina>\n" + datos_vivos["texto"] + "\n</pagina>")
    return "".join(partes)


SISTEMA_RELACIONES = """Sos un experto en trámites del Estado boliviano. Dado un trámite BASE y una lista de trámites CANDIDATOS, clasificá la relación procedimental de cada candidato respecto al base:
- siguiente_paso: el ciudadano típicamente hace el candidato DESPUÉS del base.
- requisito_previo: el candidato se necesita ANTES de poder hacer el base.
- alternativa: resuelven la misma necesidad por vías distintas.
- mismo_evento: pertenecen al mismo momento de vida pero sin orden entre sí.
- ninguna: sin relación procedimental útil (similitud solo temática o superficial).
Basate únicamente en los nombres y descripciones. Ante la duda, "ninguna"."""


def schema_relaciones(ids: list[int]) -> dict:
    return {
        "type": "object",
        "properties": {
            "relaciones": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "enum": ids},
                        "tipo": {
                            "type": "string",
                            "enum": ["siguiente_paso", "requisito_previo", "alternativa", "mismo_evento", "ninguna"],
                        },
                    },
                    "required": ["id", "tipo"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["relaciones"],
        "additionalProperties": False,
    }


def _resumen(tramite: dict) -> str:
    descripcion = (tramite.get("descripcion") or "")[:300]
    return f"{tramite['nombre']} — {descripcion}"


def usuario_relaciones(base: dict, candidatos: list[dict]) -> str:
    lineas = [f"[{c['id']}] {_resumen(c)}" for c in candidatos]
    return "BASE:\n" + _resumen(base) + "\n\nCANDIDATOS:\n" + "\n".join(lineas)
