import logging
from rich.prompt import Prompt
from clude_code.config.config import CludeConfig
from clude_code.llm.llama_cpp_http import LlamaCppHttpClient

def select_model_interactively(cfg: CludeConfig, logger: logging.Logger) -> None:
    """
    交互式模型选择逻辑，直接修改 cfg 对象的 llm.model 属性。
    """
    if cfg.llm.api_mode != "openai_compat":
        return

    client = LlamaCppHttpClient(
        base_url=cfg.llm.base_url,
        api_mode="openai_compat",
        model=cfg.llm.model,
        temperature=0.0,
        max_tokens=8,
        timeout_s=cfg.llm.timeout_s,
    )
    
    try:
        ids = client.list_model_ids()
        if not ids:
            logger.warning("未能从 /v1/models 获取模型列表（可能接口不支持）。")
            return

        logger.info("[bold]可用模型（/v1/models）[/bold]")
        for i, mid in enumerate(ids, start=1):
            logger.info(f"{i}. {mid}")
        
        try:
            # 尝试交互式输入
            sel = Prompt.ask("请选择模型序号", default="1")
            idx = int(sel)
            if 1 <= idx <= len(ids):
                cfg.llm.model = ids[idx - 1]
                logger.info(f"已选择模型: [bold cyan]{cfg.llm.model}[/bold cyan]")
            else:
                logger.warning("序号超出范围，使用默认模型。")
        except (ValueError, EOFError, KeyboardInterrupt):
            # 非交互式环境或输入错误，使用默认模型
            default_model = ids[0] if ids else cfg.llm.model
            cfg.llm.model = default_model
            logger.info(f"使用默认模型: [bold cyan]{cfg.llm.model}[/bold cyan]")
    except Exception as e:
        logger.error(f"获取模型列表失败: {e}", exc_info=True)

