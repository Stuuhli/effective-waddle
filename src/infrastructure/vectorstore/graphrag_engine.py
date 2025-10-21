"""GraphRAG engine adapter reused from legacy implementation."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, Optional

from ...config import GraphRAGSettings

LOGGER = logging.getLogger(__name__)


@dataclass
class GraphRAGQueryResult:
    """Container for GraphRAG responses."""

    text: str
    context: Dict[str, Any]
    method: str


class GraphRAGQueryEngine:
    """Caches GraphRAG config and output tables for repeated queries."""

    _OPTIONAL_TABLES = ["covariates"]
    _REQUIRED_TABLES = {
        "local": [
            "communities",
            "community_reports",
            "text_units",
            "relationships",
            "entities",
        ],
        "global": ["entities", "communities", "community_reports"],
        "drift": [
            "communities",
            "community_reports",
            "text_units",
            "relationships",
            "entities",
        ],
        "basic": ["text_units"],
    }

    def __init__(self, settings: GraphRAGSettings) -> None:
        self.settings = settings
        self.root_dir = Path(settings.root_dir).resolve()
        self.config_path = Path(settings.config_path).resolve() if settings.config_path else None
        self.default_method = settings.default_mode.lower()
        self.response_type = settings.response_type
        self.community_level = settings.community_level
        self.verbose = settings.verbose

        self._query_module: Any | None = None
        self._load_config_fn: Any | None = None
        self._create_storage_fn: Any | None = None
        self._reformat_context_fn: Any | None = None
        self._storage_has_table_fn: Any | None = None
        self._load_table_fn: Any | None = None
        self._import_exception: Exception | None = None

        self._config: Any | None = None
        self._dataframes: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    @property
    def is_ready(self) -> bool:
        return self._config is not None and bool(self._dataframes)

    def _ensure_dependencies(self) -> None:
        if self._query_module is not None and self._load_config_fn is not None:
            return
        try:
            api_module = import_module("graphrag.api")
            config_module = import_module("graphrag.config.load_config")
            models_module = import_module("graphrag.config.models.graph_rag_config")
            utils_api_module = import_module("graphrag.utils.api")
            utils_storage_module = import_module("graphrag.utils.storage")
        except Exception as exc:  # noqa: BLE001
            self._import_exception = exc
            raise RuntimeError(
                "GraphRAG dependencies are unavailable. Install the optional graphrag stack to enable this feature."
            ) from exc

        self._query_module = api_module.query
        self._load_config_fn = config_module.load_config
        self._create_storage_fn = utils_api_module.create_storage_from_config
        self._reformat_context_fn = utils_api_module.reformat_context_data
        self._storage_has_table_fn = utils_storage_module.storage_has_table
        self._load_table_fn = utils_storage_module.load_table_from_storage

    async def initialize(self) -> None:
        """Load GraphRAG configuration and output tables once."""

        self._ensure_dependencies()

        async with self._lock:
            if self.is_ready:
                return
            LOGGER.info("Loading GraphRAG config from %s", self.root_dir)
            assert self._load_config_fn is not None
            self._config = self._load_config_fn(self.root_dir, self.config_path)
            self._dataframes = await self._resolve_output_files(self._config)
            LOGGER.info("GraphRAG outputs cached for methods: %s", ", ".join(self._REQUIRED_TABLES))

    async def reload(self) -> None:
        """Force a reload of config and cached tables."""

        async with self._lock:
            self._config = None
            self._dataframes = {}
        await self.initialize()

    async def query(
        self,
        query_text: str,
        method: Optional[str] = None,
        response_type: Optional[str] = None,
    ) -> GraphRAGQueryResult:
        """Execute a GraphRAG query using the cached outputs."""

        await self.initialize()
        if not self.is_ready:
            raise RuntimeError("GraphRAG engine is not ready")

        method_name = (method or self.default_method or "local").lower()
        response_pref = response_type or self.response_type

        if method_name == "local":
            response, context = await self._run_local(query_text, response_pref)
        elif method_name == "global":
            response, context = await self._run_global(query_text, response_pref)
        elif method_name == "drift":
            response, context = await self._run_drift(query_text, response_pref)
        elif method_name == "basic":
            response, context = await self._run_basic(query_text)
        else:
            raise ValueError(f"Unsupported GraphRAG method: {method_name}")

        text = self._render_response_text(response)
        formatted_context = self._format_context(context)
        return GraphRAGQueryResult(text=text, context=formatted_context, method=method_name)

    async def _run_local(self, question: str, response_type: str) -> tuple[Any, Any]:
        assert self._config is not None
        assert self._query_module is not None
        data = self._dataframes
        if data["multi-index"]:
            covariates_list = data.get("covariates")
            if not covariates_list or len(covariates_list) != data["num_indexes"]:
                covariates_list = None
            return await self._query_module.multi_index_local_search(
                config=self._config,
                entities_list=data["entities"],
                communities_list=data["communities"],
                community_reports_list=data["community_reports"],
                text_units_list=data["text_units"],
                relationships_list=data["relationships"],
                covariates_list=covariates_list,
                index_names=data["index_names"],
                community_level=self.community_level,
                response_type=response_type,
                streaming=False,
                query=question,
                verbose=self.verbose,
            )
        return await self._query_module.local_search(
            config=self._config,
            entities=data["entities"],
            communities=data["communities"],
            community_reports=data["community_reports"],
            text_units=data["text_units"],
            relationships=data["relationships"],
            covariates=data.get("covariates"),
            community_level=self.community_level,
            response_type=response_type,
            query=question,
            verbose=self.verbose,
        )

    async def _run_global(self, question: str, response_type: str) -> tuple[Any, Any]:
        assert self._config is not None
        assert self._query_module is not None
        data = self._dataframes
        if data["multi-index"]:
            return await self._query_module.multi_index_global_search(
                config=self._config,
                entities_list=data["entities"],
                communities_list=data["communities"],
                community_reports_list=data["community_reports"],
                index_names=data["index_names"],
                community_level=self.community_level,
                dynamic_community_selection=False,
                response_type=response_type,
                streaming=False,
                query=question,
                verbose=self.verbose,
            )
        return await self._query_module.global_search(
            config=self._config,
            entities=data["entities"],
            communities=data["communities"],
            community_reports=data["community_reports"],
            community_level=self.community_level,
            dynamic_community_selection=False,
            response_type=response_type,
            query=question,
            verbose=self.verbose,
        )

    async def _run_drift(self, question: str, response_type: str) -> tuple[Any, Any]:
        assert self._config is not None
        assert self._query_module is not None
        data = self._dataframes
        if data["multi-index"]:
            return await self._query_module.multi_index_drift_search(
                config=self._config,
                entities_list=data["entities"],
                communities_list=data["communities"],
                community_reports_list=data["community_reports"],
                text_units_list=data["text_units"],
                relationships_list=data["relationships"],
                index_names=data["index_names"],
                community_level=self.community_level,
                response_type=response_type,
                streaming=False,
                query=question,
                verbose=self.verbose,
            )
        return await self._query_module.drift_search(
            config=self._config,
            entities=data["entities"],
            communities=data["communities"],
            community_reports=data["community_reports"],
            text_units=data["text_units"],
            relationships=data["relationships"],
            community_level=self.community_level,
            response_type=response_type,
            query=question,
            verbose=self.verbose,
        )

    async def _run_basic(self, question: str) -> tuple[Any, Any]:
        assert self._config is not None
        assert self._query_module is not None
        data = self._dataframes
        return await self._query_module.basic_search(
            config=self._config,
            text_units=data["text_units"],
            query=question,
            verbose=self.verbose,
        )

    async def _resolve_output_files(self, config: Any) -> Dict[str, Any]:
        assert self._create_storage_fn is not None
        assert self._storage_has_table_fn is not None
        assert self._load_table_fn is not None

        storage = await self._create_storage_fn(config, config.output)
        LOGGER.info("Loading GraphRAG outputs from %s", storage)

        async def _load_table(name: str, optional: bool = False) -> Any:
            if optional and not await self._storage_has_table_fn(storage, name):
                return None
            return await self._load_table_fn(storage, name)

        index_names, text_units, relationships, entities, communities, community_reports = await asyncio.gather(
            _load_table("index_names", optional=True),
            _load_table("text_units"),
            _load_table("relationships", optional=True),
            _load_table("entities"),
            _load_table("communities"),
            _load_table("community_reports"),
        )

        multi_index = bool(index_names)
        num_indexes = len(index_names or [])
        optional_tables = await asyncio.gather(*[_load_table(table, optional=True) for table in self._OPTIONAL_TABLES])
        return {
            "index_names": index_names,
            "text_units": text_units,
            "relationships": relationships,
            "entities": entities,
            "communities": communities,
            "community_reports": community_reports,
            "covariates": optional_tables[0] if optional_tables else None,
            "multi-index": multi_index,
            "num_indexes": num_indexes,
        }

    @staticmethod
    def _render_response_text(response: Any) -> str:
        if isinstance(response, str):
            return response
        if isinstance(response, dict) and "response_text" in response:
            return str(response["response_text"])
        return str(response)

    def _format_context(self, context: Any) -> Dict[str, Any]:
        if not context:
            return {}
        if isinstance(context, dict):
            if self._reformat_context_fn is None:
                return context
            return {key: self._reformat_context_fn(value) for key, value in context.items()}
        if self._reformat_context_fn is None:
            return {"data": context}
        return {"data": self._reformat_context_fn(context)}


__all__ = ["GraphRAGQueryEngine", "GraphRAGQueryResult"]
