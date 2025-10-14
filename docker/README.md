# 🐳 Docker Configuration

This directory contains Dockerfiles for the trading bot system.

## 📦 Images

### **web/Dockerfile**
- **Purpose:** Web dashboard for bot management
- **Base:** python:3.11-slim
- **Ports:** 8000
- **Special:** Requires Docker socket access
- **Size:** ~500MB

### **spot-trader/Dockerfile**
- **Purpose:** Spot trading bot
- **Base:** python:3.11-slim
- **Created:** Dynamically by web dashboard
- **Size:** ~450MB

### **derivative-trader/Dockerfile**
- **Purpose:** Derivative trading bot
- **Base:** python:3.11-slim
- **Created:** Dynamically by web dashboard
- **Size:** ~450MB

## 🏗️ Build Process

Images are built from the project root, not from this directory:

```bash
# From project root
docker compose build

# Or manually
docker build -f docker/web/Dockerfile -t injective-testnet-liquidity-bot-web .
docker build -f docker/spot-trader/Dockerfile -t spot-trader:latest .
docker build -f docker/derivative-trader/Dockerfile -t derivative-trader:latest .
```

## 🔧 Configuration

All images:
- Use Python 3.11
- Install from requirements.txt
- Copy necessary application code
- Set PYTHONUNBUFFERED=1
- Create /app/logs directory

## 📊 Layers

Common layers (cached):
1. Base Python image
2. System dependencies (curl)
3. Python requirements
4. Application code

Changes to application code only rebuild the last layer.

## 🎯 Best Practices

1. **.dockerignore** - Excludes unnecessary files
2. **Layer caching** - requirements.txt copied first
3. **Multi-stage possible** - Can optimize further if needed
4. **No ENTRYPOINT** - Uses CMD for flexibility

## 🔄 Updating Images

After code changes:

```bash
# Rebuild specific image
docker compose build web

# Rebuild all
docker compose build

# No-cache rebuild
docker compose build --no-cache
```

## 📏 Image Sizes (Approximate)

- **web:** 500MB (includes Docker SDK)
- **spot-trader:** 450MB
- **derivative-trader:** 450MB
- **Total:** ~1.4GB for all images

## 🚀 Production Optimization

For production, consider:
- Multi-stage builds (reduce size by 50%)
- Alpine base images (smaller, but may have compatibility issues)
- Distroless images (more secure)
- Layer optimization (combine RUN commands)

Current setup prioritizes compatibility and ease of debugging over size.

