# ==============================================================================
# Stage 1: Build production React/Vite assets
# ==============================================================================
FROM node:22-alpine AS builder

WORKDIR /app

# Copy dependency manifests and install dependencies
COPY package*.json ./
RUN npm ci || npm install

# Copy application source and build production bundle
COPY . .
RUN npm run build

# ==============================================================================
# Stage 2: Serve using hardened, non-root Nginx on port 3000
# ==============================================================================
FROM nginx:1.27-alpine AS runner

# Copy customized Nginx configuration for SPA routing on port 3000
COPY nginx.conf /etc/nginx/nginx.conf

# Copy compiled static assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Prepare temporary directories and ownership for unprivileged nginx user
RUN touch /tmp/nginx.pid \
    && chown -R nginx:nginx /tmp/nginx.pid /var/cache/nginx /var/log/nginx /usr/share/nginx/html /etc/nginx

USER nginx

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD nc -z 127.0.0.1 3000 || exit 1

CMD ["nginx", "-g", "daemon off;"]
