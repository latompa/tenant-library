"""Standalone script to run tenant seeding."""

import asyncio

from app.database import async_session_factory
from app.seed import seed_tenants


async def main():
    async with async_session_factory() as session:
        await seed_tenants(session)
        print("Tenants seeded successfully.")


if __name__ == "__main__":
    asyncio.run(main())
