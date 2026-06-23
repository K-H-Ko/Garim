FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

# 범용 환경 (소스 코드 포함)
COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]
