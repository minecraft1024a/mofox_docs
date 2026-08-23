"""MoFox 文档查询工具。

提供 LLM 可调用的文档检索能力：
- 列出文档（基于 llms.json，按 section 排序，部署指南在前）
- 按关键词检索（多关键词 AND 匹配标题 / 简介 / 预览 / 路径）
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
        "查询 Neo-MoFox 官方文档。支持列出文档（按 section 排序，部署指南在前）、"
        "按关键词检索（多关键词同时匹配，支持 offset 分页）、获取指定文档全文。"
        "当用户询问框架功能、配置、插件开发、API 用法等问题时使用。"
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
            "操作类型：list(列出文档) / search(按关键词检索) / get(获取指定文档全文)",
        ],
        query: Annotated[str | None, "检索关键词，仅 search 使用"] = None,
        doc_id: Annotated[str | None, "文档唯一标识，仅 get 使用，如 guides/configuration/bot_config_guide"] = None,
        limit: Annotated[int, "返回结果数量限制，仅 list / search 使用"] = 20,
        offset: Annotated[int, "结果偏移量，用于分页，仅 list / search 使用"] = 0,
    ) -> tuple[bool, str | dict[str, Any]]:
        """执行文档查询操作。

        Args:
            action: 操作类型
            query: 检索关键词
            doc_id: 文档唯一标识
            limit: 结果数量限制
            offset: 结果偏移量（分页）

        Returns:
            tuple[bool, str | dict]: (是否成功, 查询结果或错误信息)
        """
        try:
            client = self._get_client()

            if action == "list":
                return await self._handle_list(client, limit, offset)
            if action == "search":
                return await self._handle_search(client, query, limit, offset)
            if action == "get":
                return await self._handle_get(client, doc_id)
            return False, f"不支持的操作类型: {action}。支持的类型: list, search, get"
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
        self, client: DocsClient, limit: int, offset: int
    ) -> tuple[bool, str | dict[str, Any]]:
        """处理列出文档操作。

        使用 llms.json 索引（按 section 排序，部署类指南在前），
        每篇含 title / description / preview / section，方便定位文档。
        """
        if limit < 1:
            limit = 1
        if limit > 100:
            limit = 100
        if offset < 0:
            offset = 0

        data = await client.get_llms()
        docs = data.get("docs", [])
        page = docs[offset : offset + limit]
        output = {
            "type": "docs_index",
            "action": "list",
            "total": data.get("total", len(docs)),
            "offset": offset,
            "count": len(page),
            "docs": page,
        }
        return True, output

    async def _handle_search(
        self, client: DocsClient, query: str | None, limit: int, offset: int
    ) -> tuple[bool, str | dict[str, Any]]:
        """处理按关键词检索操作。

        文档站已移除服务端搜索，改为拉取 llms.json 索引后在本地过滤：
        查询按空白拆分为多个关键词，按"命中的关键词数量"降序返回
        （命中全部关键词的文档排最前，至少命中一个即返回）。
        匹配字段：title / description / preview / section / id / path。
        命中结果不含完整正文，需要全文时再用 action="get" 获取。
        """
        if not query:
            return False, "检索文档时必须提供 query 参数"

        if limit < 1:
            limit = 1
        if limit > 100:
            limit = 100
        if offset < 0:
            offset = 0

        tokens = [t for t in query.strip().lower().split() if t]
        data = await client.get_llms()
        docs = data.get("docs", [])

        def match_count(doc: dict[str, Any]) -> int:
            hay = " ".join(
                [
                    str(doc.get("title", "")),
                    str(doc.get("description", "")),
                    str(doc.get("preview", "")),
                    str(doc.get("section", "")),
                    str(doc.get("id", "")),
                    str(doc.get("path", "")),
                ]
            ).lower()
            return sum(1 for t in tokens if t in hay)

        scored = [(match_count(doc), i, doc) for i, doc in enumerate(docs)]
        scored = [(c, i, doc) for c, i, doc in scored if c > 0]
        scored.sort(key=lambda item: (-item[0], item[1]))
        results = [doc for _, _, doc in scored]
        page = results[offset : offset + limit]
        output = {
            "type": "docs_search_result",
            "action": "search",
            "query": query,
            "total": len(results),
            "offset": offset,
            "count": len(page),
            "results": page,
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