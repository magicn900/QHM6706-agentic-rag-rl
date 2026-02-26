import asyncio
from datetime import datetime
from pathlib import Path

from third_party_integration.lightrag_integration.wrappers import (
    create_lightrag_adapter,
    LightRAGAdapterConfig,
)


async def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    storage_dir = (
        repo_root
        / "third_party_integration"
        / "lightrag_integration"
        / "temp"
        / f"smoke_test_storage_{run_id}"
    )

    adapter = create_lightrag_adapter(
        LightRAGAdapterConfig(
            working_dir=str(storage_dir),
            use_mock=True,
        )
    )

    await adapter.initialize()
    try:
        await adapter.insert(
            "LightRAG combines vector retrieval and graph retrieval for better answers."
        )
        response = await adapter.query("What is the relationship between LightRAG and Knowledge Graph?")
        print("[OK] LightRAG mock smoke test passed.")
        print(f"[INFO] Response preview: {response[:200]}")
        print(f"[INFO] Storage path: {storage_dir}")
    finally:
        await adapter.finalize()


if __name__ == "__main__":
    asyncio.run(main())
