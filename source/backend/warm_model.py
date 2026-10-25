"""Explicit bounded warmup; no application draft and no user records are created."""
import asyncio
import json
from services.ai_service import AIService
from services.model_readiness import model_status


async def main():
    service = AIService()
    try:
        await service._prepare_model(service.default_model)
        result = await model_status()
        print(json.dumps(result))
        return 0 if result['ready'] else 1
    finally:
        await service._client.aclose()


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
