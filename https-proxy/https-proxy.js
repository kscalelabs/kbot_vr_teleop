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

// Proxy for service on 8013 (mounted at /service2)
const proxyTo8013 = createProxyMiddleware({
  target: 'http://localhost:8013',
  changeOrigin: true,
  secure: false,
  ws: true,
  pathRewrite: { '^/service2': '/' } // remove prefix before forwarding
});

// Proxy for default service on 8012 (everything else)
const proxyTo8012 = createProxyMiddleware({
  target: 'http://localhost:8012',
  changeOrigin: true,
  secure: false,
  ws: true
});

// Order matters: more specific route first
app.use('/service2', proxyTo8013);
app.use('/', proxyTo8012);

// Use port 443 (default HTTPS port)
const PORT = 443;
const server = https.createServer(options, app);

// Handle WebSocket upgrades and dispatch to the correct proxy based on URL
server.on('upgrade', (req, socket, head) => {
  if (req.url && req.url.startsWith('/service2')) {
    proxyTo8013.upgrade(req, socket, head);
  } else {
    proxyTo8012.upgrade(req, socket, head);
  }
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Proxying requests: /service2 -> http://localhost:8013, other -> http://localhost:8012`);
});
