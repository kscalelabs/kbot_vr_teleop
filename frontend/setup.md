# HTTPS Proxy Setup for Raspberry Pi

## 1. Install mkcert (for ARM64/aarch64)
```bash
curl -JLO "https://dl.filippo.io/mkcert/latest?for=linux/arm64"
chmod +x mkcert-v*-linux-arm64
sudo mv mkcert-v*-linux-arm64 /usr/local/bin/mkcert
```

## 2. setup
```bash
npm i
```

## 3. Generate SSL certificates
```bash
# Install local CA
mkcert -install
```

## 4. Run the proxy
```bash
# Start the proxy server
./run.sh
```

## 5. Access your site
Navigate to: `https://10.33.13.41` (replace with your actual IP)
