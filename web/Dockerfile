FROM node:20-slim

WORKDIR /app
COPY .yarnrc.yml package.json yarn.lock /app/
RUN corepack enable && corepack prepare yarn@4.1.1 --activate && yarn install --immutable

COPY . /app
EXPOSE 5173
CMD ["yarn", "dev", "--host", "0.0.0.0", "--port", "5173"]
