/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  // proxy /api/* to the API service when served behind nginx
  async rewrites() {
    if (process.env.NODE_ENV === 'development') {
      return [
        { source: '/api/:path*', destination: 'http://localhost:8000/:path*' },
      ];
    }
    return [];
  },
};
module.exports = nextConfig;
