FROM node:24-alpine AS build

WORKDIR /app

COPY frontend/omx-web-ui/package*.json ./
RUN npm ci

COPY frontend/omx-web-ui/ ./
RUN npm run build

FROM nginx:1.27-alpine

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080
