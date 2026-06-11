FROM node:22-alpine AS base

WORKDIR /app/apps/web

FROM base AS development

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

FROM development AS builder

RUN npm run build

FROM base AS runner

ENV NODE_ENV=production

COPY apps/web/package*.json ./
RUN npm ci --omit=dev

COPY --from=builder /app/apps/web/.next ./.next
COPY --from=builder /app/apps/web/next.config.mjs ./next.config.mjs
COPY --from=builder /app/apps/web/package.json ./package.json

RUN addgroup -S appuser \
    && adduser -S appuser -G appuser \
    && chown -R appuser:appuser /app/apps/web

USER appuser

EXPOSE 3000
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0"]
