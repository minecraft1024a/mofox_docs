"""MoFox 文档 JSON API 客户端。

封装 MoFox-Bot-Docs 文档站的 JSON API 交互逻辑，仅包含只读查询能力：
- 获取所有文档（元信息）
- 获取 LLM 检索索引（llms.json，含简介与预览，用于关键词过滤）
- 获取指定文档（含正文）

所有方法均为异步，使用 aiohttp 进行 HTTP 请求。
"""

from __future__ import annotations

from typing import Any

import aiohttp

from src.app.plugin_system.api.log_api import get_logger

logger = get_logger("mofox_docs.client")


class DocsClientError(RuntimeError):
    """文档 API 请求错误。"""


class DocsClient:
    """MoFox-Bot-Docs 文档 JSON API 客户端。

    Args:
        base_url: 文档站地址，如 "https://docs.mofox-sama.com"
        timeout: 请求超时时间（秒）
    """

    def __init__(self, base_url: str, timeout: int = 30) -> None:
        # 移除尾部斜杠以保持路径拼接一致性
        self.base_url: str = base_url.rstrip("/")
        self.timeout: int = timeout

    async def _request(self, path: str) -> dict[str, Any]:
        """发起一次 GET 请求并解析 JSON 响应。

        Args:
            path: 请求路径，以 "/api/docs" 开头

        Returns:
            解析后的 JSON 字典

        Raises:
            DocsClientError: 请求失败或响应状态异常
        """
        url = f"{self.base_url}{path}"
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise DocsClientError(
                            f"文档 API 请求失败 (HTTP {resp.status}): {url}"
                        )
                    return await resp.json()
        except aiohttp.ClientError as e:
            raise DocsClientError(f"文档 API 请求异常: {url} - {e}") from e

    async def get_index(self) -> dict[str, Any]:
        """获取所有文档（仅元信息）。

        API: GET /api/docs/index.json

        Returns:
            响应字典，包含 total 与 docs 字段
        """
        return await self._request("/api/docs/index.json")

    async def get_llms(self) -> dict[str, Any]:
        """获取 LLM 检索索引。

        API: GET /api/docs/llms.json

        文档站已移除服务端搜索（search.json / search-content.json），
        检索请使用本索引：按 section 分组排序，每篇含 title / description /
        preview（正文前 500 字符），在本地按关键词过滤后，再通过
        get_doc() 获取完整正文。

        Returns:
            响应字典，包含 title、description、version、total 与 docs 字段
        """
        return await self._request("/api/docs/llms.json")

    async def get_doc(self, doc_id: str) -> dict[str, Any]:
        """获取指定文档（含正文文本）。

        API: GET /api/docs/<id>.json

        Args:
            doc_id: 文档唯一标识，如 "guides/configuration/bot_config_guide"

        Returns:
            文档字典，包含 id、path、title、description、content 字段

        Raises:
            DocsClientError: 文档不存在或请求失败
        """
        return await self._request(f"/api/docs/{doc_id}.json")