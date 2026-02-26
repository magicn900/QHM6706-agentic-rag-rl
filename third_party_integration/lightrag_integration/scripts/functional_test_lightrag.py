import asyncio
import os
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
        / f"real_functional_test_storage_{run_id}"
    )

    adapter = create_lightrag_adapter(
        LightRAGAdapterConfig.from_env(
            working_dir=str(storage_dir),
            use_mock=False,
        )
    )

    rerank_enabled = bool(os.getenv("LIGHTRAG_RERANK_PROVIDER"))

    await adapter.initialize()
    try:
        await adapter.insert(
            "LightRAG combines graph retrieval and vector retrieval to improve answer grounding."
        )
        response = await adapter.query(
            "Explain how LightRAG uses a knowledge graph.",
            mode="hybrid",
            enable_rerank=rerank_enabled,
        )

        if (
            not response
            or response.strip().lower() in {"none", "null", ""}
            or "[no-context]" in response
        ):
            raise RuntimeError(
                "Functional test failed: query returned empty/no-context response."
            )

        print("[OK] LightRAG functional test passed.")
        print(f"[INFO] Response preview: {response[:300]}")
        print(f"[INFO] Storage path: {storage_dir}")
    finally:
        await adapter.finalize()


if __name__ == "__main__":
    asyncio.run(main())
