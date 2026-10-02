import type { NextConfig } from "next";

// NEXT_PUBLIC_API_URL is compiled into the browser bundle when the server
// starts, so a dev server started with an old (e.g. expired Quick Tunnel)
// backend URL keeps calling it until restarted -- print the value in use.
console.info(`[AI Business OS] Browser API URL: ${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000 (default)"}`);

const nextConfig: NextConfig = {
  // `next dev` blocks /_next/* (incl. the HMR socket) from non-localhost
  // origins, which prevents hydration behind the demo's Cloudflare Quick
  // Tunnel (demo.ps1). Dev-only; ignored by `next build`/`next start`.
  allowedDevOrigins: ["*.trycloudflare.com"],
};

export default nextConfig;
