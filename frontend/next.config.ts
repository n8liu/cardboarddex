import type { NextConfig } from "next";
import fs from "node:fs";
import path from "node:path";

function loadRootEnvApi(): string | undefined {
  if (process.env.NEXT_PUBLIC_API_URL?.trim()) {
    return process.env.NEXT_PUBLIC_API_URL.trim();
  }
  if (process.env.DEFAULT_API_URL?.trim()) {
    return process.env.DEFAULT_API_URL.trim();
  }
  try {
    const rootEnv = path.resolve(process.cwd(), "../.env");
    if (fs.existsSync(rootEnv)) {
      const content = fs.readFileSync(rootEnv, "utf-8");
      const match =
        content.match(/^NEXT_PUBLIC_API_URL=(.*)$/m) ||
        content.match(/^DEFAULT_API_URL=(.*)$/m);
      if (match && match[1]?.trim()) {
        const val = match[1].trim().replace(/^["']|["']$/g, "");
        process.env.NEXT_PUBLIC_API_URL = val;
        return val;
      }
    }
  } catch {}
  return undefined;
}

const envApi = loadRootEnvApi();
const DEFAULT_API_URL = envApi || "http://localhost:8000";
const resolvedApi = DEFAULT_API_URL;
const apiOrigin = new URL(resolvedApi);
const apiIsLocal = ["127.0.0.1", "localhost"].includes(apiOrigin.hostname);

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_API_URL: resolvedApi,
  },
  images: {
    dangerouslyAllowLocalIP: apiIsLocal,
    dangerouslyAllowSVG: true,
    contentDispositionType: "attachment",
    contentSecurityPolicy: "default-src 'self'; script-src 'none'; sandbox;",
    formats: ["image/avif", "image/webp"],
    minimumCacheTTL: 2_678_400,
    remotePatterns: [
      {
        protocol: apiOrigin.protocol.replace(":", "") as "http" | "https",
        hostname: apiOrigin.hostname,
        port: apiOrigin.port,
        pathname: "/cards/**",
      },
      {
        protocol: "https",
        hostname: "*.amazonaws.com",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "raw.githubusercontent.com",
        pathname: "/**",
      },
    ],
  },
};

export default nextConfig;
