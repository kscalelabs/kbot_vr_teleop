const https = require('https');
const { createProxyMiddleware } = require('http-proxy-middleware');
const express = require('express');
const fs = require('fs');
const path = require('path');

const app = express();

// SSL certificate options
const options = {
  key: fs.readFileSync(path.resolve(__dirname, '../https-proxy/cert-key.pem')),
  cert: fs.readFileSync(path.resolve(__dirname, '../https-proxy/cert.pem'))
};

// Proxy for service on 8013 (mounted at /service2)
const proxyTo8013 = createProxyMiddleware({
  target: 'http://localhost:8013',
  changeOrigin: true,
  secure: false,
  ws: true,
  pathRewrite: { '^/service2': '/' }
});

// Proxy for React dev server (8012) in development
const proxyTo8012 = createProxyMiddleware({
  target: 'http://localhost:8012',
  changeOrigin: true,
  secure: false,
  ws: true
});

// Serve static files from build in production
if (process.env.NODE_ENV === 'production') {
  app.use(express.static(path.join(__dirname, 'build')));
  app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'build', 'index.html'));
  });
} else {
  // Proxy all other requests to React dev server
  app.use('/', proxyTo8012);
}

// Proxy /service2 requests
app.use('/service2', proxyTo8013);

const PORT = process.env.PORT || 8443;
const server = https.createServer(options, app);

server.on('upgrade', (req, socket, head) => {
  if (req.url && req.url.startsWith('/service2')) {
    proxyTo8013.upgrade(req, socket, head);
  } else {
    proxyTo8012.upgrade(req, socket, head);
  }
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`HTTPS server running on port ${PORT}`);
  if (process.env.NODE_ENV === 'production') {
    console.log('Serving React build.');
  } else {
    console.log('Proxying to React dev server on 8012.');
  }
  console.log('Proxying /service2 to http://localhost:8013');
});
