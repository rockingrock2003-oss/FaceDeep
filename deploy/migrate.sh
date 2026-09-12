#!/bin/bash
set -e

echo "Running database migrations..."

# Generate migration (if needed)
# alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

echo "Migrations complete!"
