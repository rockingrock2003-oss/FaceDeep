#!/bin/bash

echo "🚀 Setting up FaceDeep..."

# Copy .env if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ Created .env from .env.example"
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Install Node dependencies for frontend
echo "📦 Installing frontend dependencies..."
cd frontend && npm install && cd ..

# Start PostgreSQL
echo "🐘 Starting PostgreSQL..."
sudo service postgresql start

# Create database and user
echo "🗄️ Setting up database..."
sudo -u postgres psql -c "CREATE USER facedeep WITH PASSWORD 'facedeep_secret';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE facedeep OWNER facedeep;" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE facedeep TO facedeep;" 2>/dev/null || true

# Start ChromaDB
echo "📊 Starting ChromaDB..."
mkdir -p chroma_data

echo ""
echo "✅ Setup complete!"
echo ""
echo "📋 To start services, run in separate terminals:"
echo "   Terminal 1: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo "   Terminal 2: cd frontend && npm run dev"
echo ""
echo "🌐 Services will be available at:"
echo "   Backend:  http://localhost:8000"
echo "   Frontend: http://localhost:3000"
echo "   API Docs: http://localhost:8000/docs"
