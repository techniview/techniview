FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
# ci, not install: lockfile is committed so builds repeat
RUN npm ci --silent

COPY . .

CMD ["npm", "run", "dev"]
