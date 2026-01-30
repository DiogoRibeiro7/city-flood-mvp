FROM node:20-slim

WORKDIR /app
COPY package.json yarn.lock /app/
RUN corepack enable && yarn install --frozen-lockfile

COPY . /app
EXPOSE 5173
CMD ["yarn", "dev", "--host", "0.0.0.0", "--port", "5173"]
