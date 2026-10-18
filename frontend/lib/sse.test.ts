import { describe, expect, it } from "vitest";
import { parsearBloques } from "./sse";

describe("parsearBloques", () => {
  it("separa eventos completos y conserva el resto", () => {
    const { eventos, resto } = parsearBloques(
      'event: answer\ndata: {"delta":"Hola"}\n\nevent: answer\ndata: {"del',
    );
    expect(eventos).toEqual([{ evento: "answer", data: { delta: "Hola" } }]);
    expect(resto).toBe('event: answer\ndata: {"del');
  });

  it("acepta CRLF y reconstruye un evento partido entre chunks", () => {
    const primero = parsearBloques("event: trace\r\ndata: {\"veredicto\":");
    const segundo = parsearBloques(primero.resto + '"claro"}\r\n\r\n');
    expect(segundo.eventos).toEqual([{ evento: "trace", data: { veredicto: "claro" } }]);
    expect(segundo.resto).toBe("");
  });

  it("descarta bloques con JSON inválido", () => {
    const { eventos } = parsearBloques("event: answer\ndata: {roto\n\n");
    expect(eventos).toEqual([]);
  });
});
