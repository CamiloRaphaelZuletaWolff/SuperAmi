import { describe, expect, it } from "vitest";
import { describir, deWhatsappAMarkdown, formatearCosto } from "./texto";

describe("deWhatsappAMarkdown", () => {
  it("convierte *negrita* de WhatsApp a markdown", () => {
    expect(deWhatsappAMarkdown("Soy *AMI*, tu asistente")).toBe("Soy **AMI**, tu asistente");
  });

  it("no toca la negrita markdown ya escrita", () => {
    expect(deWhatsappAMarkdown("Esto es **importante**")).toBe("Esto es **importante**");
  });

  it("no toca viñetas con asterisco", () => {
    expect(deWhatsappAMarkdown("* CI vigente\n* NIT")).toBe("* CI vigente\n* NIT");
  });
});

describe("describir", () => {
  it("lee objetos con nombre, dirección y url", () => {
    expect(describir({ nombre: "Plataforma", direccion: "Calle Mercado 1", url: "https://x.bo" })).toEqual({
      texto: "Plataforma, Calle Mercado 1",
      url: "https://x.bo",
    });
  });

  it("reconoce strings que son URLs y descarta vacíos", () => {
    expect(describir("https://impuestos.gob.bo")).toEqual({
      texto: "https://impuestos.gob.bo",
      url: "https://impuestos.gob.bo",
    });
    expect(describir("  ")).toBeNull();
    expect(describir({})).toBeNull();
  });
});

describe("formatearCosto", () => {
  it("usa Bs para bolivianos y deja otras monedas al final", () => {
    expect(formatearCosto(25, "Bs.")).toBe("Bs 25");
    expect(formatearCosto(25, null)).toBe("Bs 25");
    expect(formatearCosto(10, "USD")).toBe("10 USD");
  });
});
