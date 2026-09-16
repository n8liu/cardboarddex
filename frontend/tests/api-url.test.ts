import { afterEach, describe, expect, it, vi } from "vitest";
import { PRODUCTION_API_URL, resolveApiUrl } from "@/lib/api";

const LEGACY_AWS_API_URL =
  "https://ca-72b07140e03c4335a2d28f0e1c81f161.ecs.us-west-2.on.aws";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("resolveApiUrl", () => {
  it("routes a legacy Pages production URL through the tunnel", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_API_URL", LEGACY_AWS_API_URL);

    expect(resolveApiUrl()).toBe(PRODUCTION_API_URL);
  });

  it("keeps the local API during development", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000/");

    expect(resolveApiUrl()).toBe("http://localhost:8000");
  });
});
