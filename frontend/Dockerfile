FROM node:20-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN set -eux; \
	npm ci --legacy-peer-deps; \
	rollup_version=$(node -p "require('./node_modules/rollup/package.json').version"); \
	npm install --no-save "@rollup/rollup-linux-x64-musl@${rollup_version}"

COPY . .
RUN npm run build

FROM node:20-alpine AS production
WORKDIR /app

RUN npm install -g serve

COPY --from=build /app/dist ./dist

ENV PORT=8080

CMD ["sh", "-c", "serve -s dist -l $PORT"]
