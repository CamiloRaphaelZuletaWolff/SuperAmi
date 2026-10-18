import type { Metadata, Viewport } from "next";
import { Archivo } from "next/font/google";
import "./globals.css";

const archivo = Archivo({
  subsets: ["latin"],
  axes: ["wdth"],
  variable: "--fuente",
  display: "swap",
});

export const metadata: Metadata = {
  title: "AMI, asistente de trámites",
  description:
    "Pregunta por un trámite con tus palabras y AMI te dice requisitos, costo y dónde hacerlo, con la ficha oficial y cómo la encontró.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#EEF1F4" },
    { media: "(prefers-color-scheme: dark)", color: "#101A2E" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={archivo.variable}>
      <body>{children}</body>
    </html>
  );
}
