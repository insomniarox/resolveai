import type { NextConfig } from "next";

const resolveAiApiUrl = (
  process.env.RESOLVEAI_API_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  agentRules: false,
  turbopack: {
    root: process.cwd(),
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${resolveAiApiUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
