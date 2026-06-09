FROM node:22-slim

# better-sqlite3 needs build tools
RUN apt-get update && apt-get install -y python3 make g++ && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies
COPY package.json package-lock.json* ./
RUN npm ci

# Copy source
COPY . .

# Create data directory for SQLite
RUN mkdir -p data

# Run the signal engine (cron schedules 9AM ET daily)
CMD ["npx", "tsx", "src/engine/index.ts"]
