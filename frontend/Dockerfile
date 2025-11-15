# syntax=docker/dockerfile:1
ARG VITE_WEATHER_AGENT_URL="/api/weather/forecast"

FROM node:20-alpine AS build
ARG VITE_WEATHER_AGENT_URL
ENV VITE_WEATHER_AGENT_URL=${VITE_WEATHER_AGENT_URL}
WORKDIR /app

COPY package*.json ./
RUN npm ci --legacy-peer-deps

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS production
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
