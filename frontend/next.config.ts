import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits a self-contained server bundle with only the dependencies actually
  // reached. The Docker image copies that instead of node_modules, which is the
  // difference between a ~200 MB image and a ~1 GB one.
  output: "standalone",

  // The browser never calls the FastAPI service directly — every request goes
  // through the route handler in src/app/api. That is why the backend needs no
  // CORS middleware: there is no cross-origin request to permit.
  reactStrictMode: true,
};

export default nextConfig;
