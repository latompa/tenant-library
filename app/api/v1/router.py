from fastapi import APIRouter

v1_router = APIRouter()

# All tenant-scoped routes will be mounted under /tenants/{tenant_slug}/
# Sub-routers are included here as they are implemented.
