import type { NextConfig } from "next";

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const esDev = process.env.NODE_ENV !== "production";

// CSP conservadora: Next (App Router) mete <script> inline para hidratar, así que
// script-src necesita 'unsafe-inline' salvo que se usen nonces (eso obliga a
// render dinámico vía middleware: no vale la pena para un sitio estático).
// Lo que sí cierra: de dónde se cargan cosas, a quién se le habla (solo al API),
// plugins, <base>, formularios y que nadie embeba la página en un iframe.
// next/font sirve la fuente desde el mismo dominio: no hace falta fonts.googleapis.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${esDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  `connect-src 'self' ${API_URL}`,
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
