FROM node:22-alpine AS build
WORKDIR /src
COPY package.json tsconfig.json index.ts ./
RUN npm install
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /src/node_modules ./node_modules
COPY --from=build /src/dist ./dist
EXPOSE 29981
USER node
CMD ["node", "dist/index.js"]
