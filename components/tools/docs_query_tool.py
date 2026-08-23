"""MoFox 文档查询工具。

提供 LLM 可调用的文档检索能力：
- 获取所有文档列表
- 按标题 / 路径 / id 搜索
- 按正文内容搜索
- 获取指定文档的完整内容

所有查询均为只读操作，不产生任何副作用。
"""

from __future__ import annotations

from typing import Annotated, Any, TYPE_CHECKING

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import BaseTool
from src.app.plugin_system.types import ChatType

from ...config import MofoxDocsConfig
from ...utils.docs_client import DocsClient, DocsClientError

if TYPE_CHECKING:
    from src.core.components.base import BasePlugin

logger = get_logger("mofox_docs.tool")


class DocsQueryTool(BaseTool):
    """MoFox 文档查询工具。

    通过 MoFox-Bot-Docs 文档 JSON API 查询 Neo-MoFox 官方文档，
    供 LLM 检索和阅读文档内容。
    """

    chat_type = ChatType.ALL
    associated_platforms: list[str] = []

    name: str = "docs_query"
    description: str = (
        "查询 Neo-MoFox 官方文档。支持按标题搜索、按正文搜索、获取指定文档全文、"
        "以及列出所有文档。当用户询问框架功能、配置、插件开发、API 用法等问题时使用。"
    )

    def __init__(self, plugin: "BasePlugin") -> None:
        """初始化文档查询工具。

        Args:
            plugin: 所属插件实例
        """
        super().__init__(plugin)

        self._config: MofoxDocsConfig | None = None
        if isinstance(self.plugin.config, MofoxDocsConfig):
            self._config = self.plugin.config
        else:
            logger.warning("插件配置类型不匹配，将使用默认配置")

        self._client: DocsClient | None = None

    def _get_client(self) -> DocsClient:
        """获取或创建文档客户端实例。

        Returns:
            文档 API 客户端
        """
        if self._client is None:
            base_url = self._get_base_url()
            timeout = self._get_timeout()
            self._client = DocsClient(base_url=base_url, timeout=timeout)
            logger.debug(f"文档客户端已初始化: {base_url}, timeout={timeout}s")
        return self._client

    def _get_base_url(self) -> str:
        """从配置获取文档站地址。"""
        if self._config:
            return self._config.server.base_url
        return "https://docs.mofox-sama.com"

    def _get_timeout(self) -> int:
        """从配置获取请求超时时间。"""
        if self._config:
            return self._config.server.timeout
        return 30

    def _get_default_limit(self) -> int:
        """从配置获取默认返回结果数量。"""
        if self._config:
            return self._config.search.default_limit
        return 20

    async def execute(
        self,
        action: Annotated[
            str,
            "操作类型：list(列出所有文档) / search(按标题、路径或 id 搜索) "
            "/ search_content(按正文内容搜索) / get(获取指定文档全文)",
        ],
        query: Annotated[str | None, "搜索关键词，仅 search / search_content 使用"] = None,
        doc_id: Annotated[str | None, "文档唯一标识，仅 get 使用，如 guides/configuration/bot_config_guide"] = None,
        limit: Annotated[int, "返回结果数量限制，仅 list / search / search_content 使用"] = 20,
    ) -> tuple[bool, str | dict[str, Any]]:
        """执行文档查询操作。

        Args:
            action: 操作类型
            query: 搜索关键词
            doc_id: 文档唯一标识
            limit: 结果数量限制

        Returns:
            tuple[bool, str | dict]: (是否成功, 查询结果或错误信息)
        """
        try:
            client = self._get_client()

            if action == "list":
                return await self._handle_list(client, limit)
            if action == "search":
                return await self._handle_search(client, query, limit)
            if action == "search_content":
                return await self._handle_search_content(client, query, limit)
            if action == "get":
                return await self._handle_get(client, doc_id)
            return False, (
                f"不支持的操作类型: {action}。支持的类型: list, search, search_content, get"
            )
        except DocsClientError as e:
            logger.error(f"文档查询失败: action={action}, query={query}, doc_id={doc_id} - {e}")
            return False, f"文档查询失败: {e}"
        except Exception as e:
            logger.error(
                f"文档查询异常: action={action}, query={query}, doc_id={doc_id} - {e}",
                exc_info=True,
            )
            return False, f"执行查询时发生错误: {e}"

    async def _handle_list(
        self, client: DocsClient, limit: int
    ) -> tuple[bool, str | dict[str, Any]]:
        """处理列出所有文档操作。"""
        if limit < 1:
            limit = 1
        if limit > 100:
            limit = 100

        data = await client.get_index()
        docs = data.get("docs", [])
        output = {
            "type": "docs_index",
            "action": "list",
            "total": data.get("total", len(docs)),
            "count": min(limit, len(docs)),
            "docs": docs[:limit],
        }
        return True, output

    async def _handle_search(
        self, client: DocsClient, query: str | None, limit: int
    ) -> tuple[bool, str | dict[str, Any]]:
        """处理按标题 / 路径 / id 搜索操作。"""
        if not query:
            return False, "搜索文档时必须提供 query 参数"

        data = await client.search(query)
        results = data.get("results", [])
        output = {
            "type": "docs_search_result",
            "action": "search",
            "query": data.get("query", query),
            "total": data.get("total", len(results)),
            "count": min(limit, len(results)),
            "results": results[:limit],
        }
        return True, output

    async def _handle_search_content(
        self, client: DocsClient, query: str | None, limit: int
    ) -> tuple[bool, str | dict[str, Any]]:
        """处理按正文内容搜索操作。"""
        if not query:
            return False, "按正文搜索时必须提供 query 参数"

        data = await client.search_content(query)
        results = data.get("results", [])
        output = {
            "type": "docs_content_search_result",
            "action": "search_content",
            "query": data.get("query", query),
            "total": data.get("total", len(results)),
            "count": min(limit, len(results)),
            "results": results[:limit],
        }
        return True, output

    async def _handle_get(
        self, client: DocsClient, doc_id: str | None
    ) -> tuple[bool, str | dict[str, Any]]:
        """处理获取指定文档操作。"""
        if not doc_id:
            return False, "获取文档时必须提供 doc_id 参数"

        doc = await client.get_doc(doc_id)
        output = {
            "type": "docs_doc",
            "action": "get",
            "doc": doc,
        }
        return True, output