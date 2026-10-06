// Static export: `npm run build` writes plain HTML/CSS/JS to out/, which any static host serves
// (Vercel, GitHub Pages, a static Hugging Face Space). There is no server code and no secrets.
//
// Configuration (build time - rebuild after changing):
//   NEXT_PUBLIC_API_URL   Base URL of the backend API, e.g. https://you-scam-detector-api.hf.space
//                         Empty/unset in a production build = the backend is not hosted yet: the site
//                         runs in demo mode (recorded real responses for the samples only).
//                         `npm run dev` defaults to the local API at http://127.0.0.1:7860.
//   NEXT_PUBLIC_BASE_PATH Sub-path the site is served from (GitHub Pages project sites), e.g. /scam-detector
//   NEXT_PUBLIC_REPO_URL  Optional link to the GitHub repository, shown on the About page (hidden if unset).

const isDev = process.env.NODE_ENV === "development";
const rawApiUrl = process.env.NEXT_PUBLIC_API_URL ?? (isDev ? "http://127.0.0.1:7860" : "");
const apiUrl = rawApiUrl.trim().replace(/\/+$/, "");
const basePath = (process.env.NEXT_PUBLIC_BASE_PATH ?? "").trim().replace(/\/+$/, "");
const repoUrl = (process.env.NEXT_PUBLIC_REPO_URL ?? "").trim();

if (apiUrl && !/^https?:\/\/[^\s/]+$/i.test(apiUrl)) {
  throw new Error(`NEXT_PUBLIC_API_URL must be an origin like https://host (no path), got: ${apiUrl}`);
}
if (repoUrl && !/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/?$/i.test(repoUrl)) {
  throw new Error(`NEXT_PUBLIC_REPO_URL must look like https://github.com/<owner>/<repo>, got: ${repoUrl}`);
}
if (basePath && !/^\/[\w./-]+$/.test(basePath)) {
  throw new Error(`NEXT_PUBLIC_BASE_PATH must look like /my-path, got: ${basePath}`);
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  reactStrictMode: true,
  poweredByHeader: false,
  images: { unoptimized: true },
  ...(basePath ? { basePath } : {}),
  // Inlined into the client bundle at build time (non-secret values only).
  env: {
    SCAM_API_URL: apiUrl,
    SCAM_BASE_PATH: basePath,
    SCAM_REPO_URL: repoUrl,
  },
};

export default nextConfig;
