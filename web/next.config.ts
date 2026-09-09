import type { NextConfig } from 'next';

// The UI has no server-rendered data dependencies. Export it as static files so
// FastAPI can serve the complete application from a single production image.
const nextConfig: NextConfig = {
  output: 'export',
};

export default nextConfig;
