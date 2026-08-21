import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits .next/standalone with a self-contained server.js and only the
  // node_modules actually reached, so the production image does not ship the
  // full dependency tree. Required by apps/web/Dockerfile.
  output: "standalone",
};

export default nextConfig;
