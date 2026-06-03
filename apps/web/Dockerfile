FROM node:22-alpine

WORKDIR /app/apps/web

COPY apps/web/package*.json ./
RUN npm ci

COPY apps/web ./

RUN addgroup -S appuser \
    && adduser -S appuser -G appuser \
    && mkdir -p /app/apps/web/.next /app/apps/web/node_modules \
    && chown -R appuser:appuser /app/apps/web \
    && chmod +x /app/apps/web/docker-entrypoint.sh

EXPOSE 3000
ENTRYPOINT ["/app/apps/web/docker-entrypoint.sh"]
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--webpack"]
