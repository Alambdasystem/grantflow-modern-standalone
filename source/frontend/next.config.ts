import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // CPU inference can take longer than Next's default rewrite timeout.
  experimental: { proxyTimeout: 420_000, middlewareClientMaxBodySize: 21 * 1024 * 1024 },
  distDir: process.env.GFM_DIST_DIR || ".next",
  basePath: "/gfm-app",
  assetPrefix: "/gfm-app",
  // Don't 308 POST /api/foo/ -> /api/foo. FastAPI requires the trailing slash on
  // collection routes; without this, the redirect strips the slash, then FastAPI
  // 307s to an absolute upstream URL which the browser treats as cross-origin
  // (drops Authorization header), causing "Could not start AI application".
  skipTrailingSlashRedirect: true,
  outputFileTracingRoot: path.join(__dirname, "..", ".."),
  async redirects() {
    return [
      {
        source: "/",
        destination: "/gfm-app/dashboard",
        permanent: false,
        basePath: false,
      },
    ];
  },
  async rewrites() {
    return [
      // Preserve trailing slash so FastAPI collection routes (e.g. /applications/)
      // don't 307 to an absolute upstream URL (which becomes cross-origin in the
      // browser and strips the Authorization header).
      {
        source: "/api/:path*/",
        destination: `${process.env.GFM_BACKEND_URL || "http://127.0.0.1:8001"}/api/:path*/`,
      },
      {
        source: "/api/:path*",
        destination: `${process.env.GFM_BACKEND_URL || "http://127.0.0.1:8001"}/api/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "X-Content-Type-Options", value: "nosniff" },
        ],
      },
    ];
  },
};

export default nextConfig;
