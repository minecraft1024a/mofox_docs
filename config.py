"""MoFox 文档查询插件配置。"""

from __future__ import annotations

from typing import ClassVar

from src.app.plugin_system.base import BaseConfig, Field, SectionBase, config_section


class MofoxDocsConfig(BaseConfig):
    """MoFox 文档查询插件配置。

    管理文档站的连接配置与搜索默认值。
    """

    name: ClassVar[str] = "config"
    description: ClassVar[str] = "MoFox 文档查询插件配置"

    @config_section("server", title="文档站配置", tag="network")
    class ServerSection(SectionBase):
        """文档站服务连接配置。"""

        base_url: str = Field(
            default="https://docs.mofox.chat",
            description="MoFox-Bot-Docs 文档站地址，如 https://docs.mofox.chat",
            label="文档站地址",
            tag="network",
            order=0,
        )
        timeout: int = Field(
            default=30,
            description="请求超时时间（秒）",
            label="请求超时",
            ge=5,
            le=120,
            tag="network",
            order=1,
        )

    @config_section("search", title="搜索配置", tag="general")
    class SearchSection(SectionBase):
        """搜索默认配置。"""

        default_limit: int = Field(
            default=20,
            description="默认返回结果数量限制（1-100）",
            label="默认结果数量",
            ge=1,
            le=100,
            tag="general",
            order=0,
        )

    server: ServerSection = Field(default_factory=ServerSection)
    search: SearchSection = Field(default_factory=SearchSection)