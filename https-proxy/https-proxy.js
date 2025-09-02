const https = require('https');
const { createProxyMiddleware } = require('http-proxy-middleware');
const express = require('express');
const fs = require('fs');

const app = express();

const ip = '10.33.13.41'

// SSL certificate options (update IP to match your certificate)
const options = {
  key: fs.readFileSync(`./${ip}+3-key.pem`),
  cert: fs.readFileSync(`./${ip}+3.pem`)
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
  console.log(`HTTPS proxy server running on https://${ip}`);
  console.log(`Proxying requests to http://localhost:8012`);
});
