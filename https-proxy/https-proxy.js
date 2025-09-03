const https = require('https');
const { createProxyMiddleware } = require('http-proxy-middleware');
const express = require('express');
const fs = require('fs');

const app = express();

// SSL certificate options (update IP to match your certificate)
const options = {
  key: fs.readFileSync(`./cert-key.pem`),
  cert: fs.readFileSync(`./cert.pem`)
};

// Create proxy middleware with WebSocket support
const proxy = createProxyMiddleware({
  target: 'http://localhost:8012',
  changeOrigin: true,
  secure: false,
  ws: true
});

app.use('/', proxy);

// Use port 443 (default HTTPS port)
const PORT = 443;
const server = https.createServer(options, app);

// Enable WebSocket upgrade handling
server.on('upgrade', proxy.upgrade);

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Proxying requests to http://localhost:8012`);
});
