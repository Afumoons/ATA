import type { NextConfig } from "next";

const UI_API_ORIGIN = process.env.UI_API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactCompiler: true,
  turbopack: {
    root: __dirname,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${UI_API_ORIGIN}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
