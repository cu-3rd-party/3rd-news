FROM oven/bun:1-alpine
WORKDIR /srv

COPY package.json ./
RUN bun install

COPY . .

EXPOSE 5173
CMD ["bun", "run", "dev"]
