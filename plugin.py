"""MoFox 文档查询插件入口。

通过 MoFox-Bot-Docs 文档 JSON API 提供文档检索能力：
- 获取所有文档列表
- 按标题 / 路径 / id 搜索
- 按正文内容搜索
- 获取指定文档的完整内容
"""

from __future__ import annotations

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import BasePlugin, register_plugin

from .components.tools.docs_query_tool import DocsQueryTool
from .config import MofoxDocsConfig

logger = get_logger("mofox_docs")


@register_plugin
class MofoxDocsPlugin(BasePlugin):
    """MoFox 文档查询插件。

    提供文档站 JSON API 的查询能力，供 LLM 检索 Neo-MoFox 官方文档。
    """

    plugin_name: str = "mofox_docs"
    plugin_description: str = "通过 MoFox-Bot-Docs 文档 JSON API 查询和获取 Neo-MoFox 官方文档"
    plugin_version: str = "1.1.1"

    configs: list[type] = [MofoxDocsConfig]
    dependent_components: list[str] = []

    async def on_plugin_loaded(self) -> None:
        """插件加载完成后的生命周期钩子。"""
        logger.info("MoFox 文档查询插件已加载")

    async def on_plugin_unloaded(self) -> None:
        """插件卸载时的清理钩子。"""
        logger.info("MoFox 文档查询插件已卸载")

    def get_components(self) -> list[type]:
        """返回插件包含的组件类。"""
        return [DocsQueryTool]