import type { NextConfig } from "next";

const DEFAULT_API_URL =
  "https://ca-72b07140e03c4335a2d28f0e1c81f161.ecs.us-west-2.on.aws";
const envApi = process.env.NEXT_PUBLIC_API_URL?.trim();
const resolvedApi = (!envApi || envApi.includes("api.cardboarddex.com"))
  ? DEFAULT_API_URL
  : envApi;
const apiOrigin = new URL(resolvedApi);
const apiIsLocal = ["127.0.0.1", "localhost"].includes(apiOrigin.hostname);

const nextConfig: NextConfig = {
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
        hostname: "ca-72b07140e03c4335a2d28f0e1c81f161.ecs.us-west-2.on.aws",
        pathname: "/cards/**",
      },
      {
        protocol: "https",
        hostname: "cardboarddex-card-assets-349558247779.s3.us-west-2.amazonaws.com",
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
