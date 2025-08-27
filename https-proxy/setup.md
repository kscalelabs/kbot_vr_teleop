# HTTPS Proxy Setup for Raspberry Pi

## 1. Install mkcert (for ARM64/aarch64)
```bash
curl -JLO "https://dl.filippo.io/mkcert/latest?for=linux/arm64"
chmod +x mkcert-v*-linux-arm64
sudo mv mkcert-v*-linux-arm64 /usr/local/bin/mkcert
```

## 2. Create project folder and setup
```bash
# Create project directory
mkdir https-proxy
cd https-proxy

# Initialize npm project
npm init -y

# Install required packages
npm install express http-proxy-middleware
```

## 3. Generate SSL certificates
```bash
# Install local CA
mkcert -install

# Create certificate for your IP (replace with your actual IP)
mkcert 10.33.12.254 localhost 127.0.0.1 ::1
```

## 4. Create the proxy server
Create `https-proxy.js`:

```javascript
const https = require('https');
const { createProxyMiddleware } = require('http-proxy-middleware');
const express = require('express');
const fs = require('fs');

const app = express();

// SSL certificate options (update IP to match your certificate)
const options = {
  key: fs.readFileSync('./10.33.13.41+3-key.pem'),
  cert: fs.readFileSync('./10.33.13.41+3.pem')
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
  console.log(`HTTPS proxy server running on https://10.33.13.41`);
  console.log(`Proxying requests to http://localhost:8012`);
});
```

## 5. Run the proxy
```bash
# Start the proxy server
sudo -E env "PATH=$PATH" node https-proxy.js
```

## 6. Access your site
Navigate to: `https://10.33.13.41` (replace with your actual IP)

## File Structure
After setup, your folder should contain:
```
https-proxy/
├── package.json
├── package-lock.json
├── node_modules/
├── https-proxy.js
├── 10.33.13.41+3.pem
└── 10.33.13.41+3-key.pem
```

## Notes
- Replace `10.33.13.41` with your actual Raspberry Pi IP address
- Replace `8012` with your actual local server port
- The proxy supports both HTTP requests and WebSocket connections
- Certificates are trusted locally; other devices may show security warnings
