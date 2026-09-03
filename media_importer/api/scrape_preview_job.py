import time

from media_importer.api import globals

_SCRAPE_PREVIEW_JOBS = {}
_PREVIEW_STEP_DELAY = 0.8


def _preview_step_delay():
    """步骤间微小延迟，让前端有时间逐条渲染进度。"""
    time.sleep(_PREVIEW_STEP_DELAY)


def _preview_add_step(job, key, label, status="running", message="", data=None):
    now = time.time()
    job["updated_at"] = now
    step_elapsed = 0.0
    if job["steps"]:
        last_step = job["steps"][-1]
        if last_step.get("key") == key and last_step.get("status") == "running":
            step_elapsed = round(now - last_step.get("_started_at", now), 2)
    job["steps"].append({
        "key": key,
        "label": label,
        "status": status,
        "message": message,
        "elapsed": round(now - job["started_at"], 2),
        "step_elapsed": step_elapsed,
        "_started_at": now,
        "data": data or {},
    })


def _find_provider(providers, provider_type):
    for p in providers:
        if p.provider_type == provider_type:
            return p
    return None


def _run_scrape_preview_job(job_id, filename, config):
    job = _SCRAPE_PREVIEW_JOBS.get(job_id)
    if not job:
        return

    logger = globals._global_logger
    try:
        from media_importer.features.providers import create_providers
        from media_importer.features.scraping import FilenameCleaner
        from media_importer.features.scraping.match_engine import MatchEngine

        _preview_add_step(job, "clean", "文件名清洗", "running", f"正在清洗：{filename}")
        _preview_step_delay()
        cleaner = FilenameCleaner()
        clean_result = cleaner.clean(filename)
        _preview_add_step(job, "clean", "文件名清洗", "done",
                          f"标题={clean_result.clean_title}，季={clean_result.season or '-'}，集={clean_result.episode or '-'}",
                          {"clean_title": clean_result.clean_title, "year": clean_result.year,
                           "season": clean_result.season, "episode": clean_result.episode})

        _preview_add_step(job, "provider_init", "Provider 初始化", "running", "正在加载 Provider 配置...")
        _preview_step_delay()
        providers = create_providers(config)
        if not providers:
            _preview_add_step(job, "provider_init", "Provider 初始化", "done", "未配置 Provider")
            job["status"] = "done"
            job["result"] = {
                "filename": filename,
                "clean_result": {
                    "clean_title": clean_result.clean_title,
                    "year": clean_result.year,
                    "season": clean_result.season,
                    "episode": clean_result.episode,
                    "method": clean_result.method,
                    "removed_items": clean_result.removed_items,
                },
                "scrape_result": {
                    "title_cn": clean_result.clean_title,
                    "title_en": "",
                    "year": clean_result.year,
                    "media_type": "tv" if clean_result.season else "movie",
                    "season": clean_result.season,
                    "episode": clean_result.episode,
                    "provider_type": "",
                    "provider_id": "",
                    "dimensions": {},
                    "match_level": "NEEDS_CONFIRM",
                    "match_tier": 0,
                    "tier_short_reason": "未配置 Provider，无法自动匹配",
                    "ai_reason": "",
                    "selected_candidate": None,
                },
                "scrape_elapsed": round(time.time() - job["started_at"], 2),
                "match_result": {
                    "match_level": "NEEDS_CONFIRM",
                    "concerns": [{"code": "NO_PROVIDER", "message": "未配置 Provider"}],
                    "candidates": [],
                },
                "import_path": {"import_path": "", "used_fallback": False, "matched_rule": None},
            }
            job["updated_at"] = time.time()
            return

        provider_names = ", ".join(p.display_name for p in providers)
        _preview_add_step(job, "provider_init", "Provider 初始化", "done",
                          f"已加载 {len(providers)} 个 Provider：{provider_names}")

        _preview_add_step(job, "match_tier1", "第1级：Provider精确匹配", "running",
                          f"正在搜索：{clean_result.clean_title}")
        _preview_step_delay()
        match_engine = MatchEngine(config)
        # 手动执行两级匹配，每级之间上报进度
        clean_title = clean_result.clean_title or ""
        cjk_title = clean_result.cjk_title or ""
        year = clean_result.year
        season = clean_result.season
        episode = clean_result.episode

        if not clean_title and not cjk_title:
            match_result = match_engine.match(filename=filename, providers=providers, conn=None, video_path=filename)
        else:
            # 第一级
            tier1_result = match_engine._tier1_exact_match(
                clean_title, cjk_title, year, season, episode, providers
            )
            if tier1_result:
                _preview_add_step(job, "match_tier1", "第1级：Provider精确匹配", "done",
                                  f"精确匹配成功：{tier1_result.provider_title}",
                                  {"match_level": "AUTO_PASS"})
                match_result = tier1_result
            else:
                _preview_add_step(job, "match_tier1", "第1级：Provider精确匹配", "done",
                                  "未找到精确匹配，进入第2级",
                                  {"match_level": "pending"})
                _preview_step_delay()

                # 第二级：用户确认（ADR-0010：原 AI 纠正级已移除）
                _preview_add_step(job, "match_tier2", "第2级：用户确认候选", "running",
                                  "收集候选列表供用户选择...")
                _preview_step_delay()
                match_result = match_engine._tier2_user_confirm(
                    clean_title, cjk_title, year, season, episode, providers
                )
                _preview_add_step(job, "match_tier2", "第2级：用户确认候选", "done",
                                  f"需人工确认，共 {len(match_result.candidates)} 个候选",
                                  {"match_level": "NEEDS_CONFIRM"})

        match_dict = match_result.to_dict()

        _preview_add_step(job, "scrape", "生成刮削结果", "running", "正在获取详情...")
        _preview_step_delay()
        scrape_result = {}
        cached_details = None
        cached_provider = None
        match_level = match_dict.get("match_level", "NEEDS_CONFIRM")
        candidates = match_dict.get("candidates", [])

        if match_level == "FAILED":
            _preview_add_step(job, "scrape", "刮削结果", "done", "AI 判定非影视文件，任务失败")
            scrape_result = {
                "title_cn": clean_result.clean_title or "",
                "year": None,
                "media_type": "",
                "match_level": "FAILED",
                "match_tier": match_result.match_tier,
                "tier_short_reason": match_dict.get("tier_short_reason", ""),
                "ai_reason": match_dict.get("ai_reason", ""),
                "selected_candidate": None,
                "dimensions": {},
            }
            _preview_add_step(job, "scrape", "生成刮削结果", "done",
                              "AI 判定非影视文件",
                              {"title": ""})
            scrape_elapsed = round(time.time() - job["started_at"], 2)
            job["status"] = "done"
            job["result"] = {
                "filename": filename,
                "clean_result": {
                    "clean_title": clean_result.clean_title,
                    "year": clean_result.year,
                    "season": clean_result.season,
                    "episode": clean_result.episode,
                    "method": clean_result.method,
                    "removed_items": clean_result.removed_items,
                },
                "scrape_result": scrape_result,
                "scrape_elapsed": scrape_elapsed,
                "match_result": match_dict,
                "import_path": {"import_path": "", "used_fallback": False, "matched_rule": None},
            }
            job["updated_at"] = time.time()
            return

        if match_level in ("AUTO_PASS", "CONTEXT_PASS"):
            provider_id = match_result.provider_id
            provider_title = match_result.provider_title
            matched_candidate = None
            for c in candidates:
                if str(c.get("id")) == str(provider_id):
                    matched_candidate = c
                    break

            if logger:
                logger.info(f"[scrape_preview_job] match_level={match_level}, candidates={len(candidates)}, matched={matched_candidate is not None}, provider_id={provider_id}")
            if matched_candidate:
                provider_type = matched_candidate.get("provider_type", "")
                media_type = matched_candidate.get("media_type", "movie")
                provider = _find_provider(providers, provider_type)
                if logger:
                    logger.info(f"[scrape_preview_job] provider_type={provider_type}, provider={provider is not None}")
                if provider:
                    try:
                        details = provider.get_details(str(provider_id), media_type)
                        cached_details = details
                        cached_provider = provider
                        scrape_result = {
                            "title_cn": details.title,
                            "title_en": details.original_title,
                            "year": details.year,
                            "media_type": media_type,
                            "season": clean_result.season,
                            "episode": clean_result.episode,
                            "provider_type": provider_type,
                            "provider_id": str(provider_id),
                            "poster_url": details.poster_url,
                            "overview": details.overview,
                            "dimensions": {},
                            "match_level": match_level,
                            "match_tier": match_result.match_tier,
                            "tier_short_reason": match_dict.get("tier_short_reason", ""),
                            "ai_reason": match_dict.get("ai_reason", ""),
                            "selected_candidate": match_dict.get("selected_candidate"),
                        }
                    except Exception as e:
                        if logger:
                            logger.warning(f"[scrape_preview_job] 获取详情失败: {e}")
                if not scrape_result:
                    scrape_result = {
                        "title_cn": provider_title or clean_result.clean_title,
                        "title_en": matched_candidate.get("original_title", ""),
                        "year": matched_candidate.get("year") or clean_result.year,
                        "media_type": media_type,
                        "season": clean_result.season,
                        "episode": clean_result.episode,
                        "provider_type": provider_type,
                        "provider_id": str(provider_id),
                        "dimensions": {},
                        "match_level": match_level,
                        "match_tier": match_result.match_tier,
                        "tier_short_reason": match_dict.get("tier_short_reason", ""),
                        "ai_reason": match_dict.get("ai_reason", ""),
                        "selected_candidate": match_dict.get("selected_candidate"),
                    }
            else:
                scrape_result = {
                    "title_cn": provider_title or clean_result.clean_title,
                    "title_en": "",
                    "year": clean_result.year,
                    "media_type": "tv" if clean_result.season else "movie",
                    "season": clean_result.season,
                    "episode": clean_result.episode,
                    "provider_type": "",
                    "provider_id": str(provider_id) if provider_id else "",
                    "dimensions": {},
                    "match_level": match_level,
                    "match_tier": match_result.match_tier,
                    "tier_short_reason": match_dict.get("tier_short_reason", ""),
                    "ai_reason": match_dict.get("ai_reason", ""),
                    "selected_candidate": match_dict.get("selected_candidate"),
                }

        elif match_level == "NEEDS_CONFIRM" and candidates:
            candidate = candidates[0]
            provider_type = candidate.get("provider_type", "")
            provider = _find_provider(providers, provider_type)
            media_type = candidate.get("media_type", "movie")

            if provider:
                try:
                    details = provider.get_details(str(candidate.get("id")), media_type)
                    cached_details = details
                    cached_provider = provider
                    scrape_result = {
                        "title_cn": details.title,
                        "title_en": details.original_title,
                        "year": details.year,
                        "media_type": media_type,
                        "season": clean_result.season,
                        "episode": clean_result.episode,
                        "provider_type": provider_type,
                        "provider_id": str(candidate.get("id", "")),
                        "poster_url": details.poster_url,
                        "overview": details.overview,
                        "dimensions": {},
                        "match_level": "NEEDS_CONFIRM",
                        "match_tier": match_result.match_tier,
                        "tier_short_reason": match_dict.get("tier_short_reason", ""),
                        "ai_reason": match_dict.get("ai_reason", ""),
                        "selected_candidate": match_dict.get("selected_candidate"),
                    }
                except Exception as e:
                    if logger:
                        logger.warning(f"[scrape_preview_job] 获取候选详情失败: {e}")

            if not scrape_result:
                scrape_result = {
                    "title_cn": candidate.get("title", clean_result.clean_title),
                    "title_en": candidate.get("original_title", ""),
                    "year": candidate.get("year") or clean_result.year,
                    "media_type": media_type,
                    "season": clean_result.season,
                    "episode": clean_result.episode,
                    "provider_type": provider_type,
                    "provider_id": str(candidate.get("id", "")),
                    "poster_url": candidate.get("poster_url", ""),
                    "overview": candidate.get("overview", ""),
                    "dimensions": {},
                    "match_level": "NEEDS_CONFIRM",
                    "match_tier": match_result.match_tier,
                    "tier_short_reason": match_dict.get("tier_short_reason", ""),
                    "ai_reason": match_dict.get("ai_reason", ""),
                    "selected_candidate": match_dict.get("selected_candidate"),
                }

        else:
            scrape_result = {
                "title_cn": clean_result.clean_title,
                "title_en": "",
                "year": clean_result.year,
                "media_type": "tv" if clean_result.season else "movie",
                "season": clean_result.season,
                "episode": clean_result.episode,
                "provider_type": "",
                "provider_id": "",
                "dimensions": {},
                "match_level": "NEEDS_CONFIRM",
                "match_tier": match_result.match_tier,
                "tier_short_reason": match_dict.get("tier_short_reason", "") or "未找到可用候选，需要人工确认",
                "ai_reason": match_dict.get("ai_reason", ""),
                "selected_candidate": match_dict.get("selected_candidate"),
            }

        _preview_add_step(job, "scrape", "生成刮削结果", "done",
                          f"标题={scrape_result.get('title_cn', '')}",
                          {"title": scrape_result.get("title_cn", "")})

        # 维度推导：从 Provider 详情推导 animation/documentary/restricted_level 等维度
        if logger:
            logger.info(f"[scrape_preview_job] 维度推导检查: cached_details={cached_details is not None}, cached_provider={cached_provider is not None}")
        if cached_details and cached_provider:
            _preview_add_step(job, "scrape", "维度推导", "running", "正在从 Provider 数据推导维度...")
            _preview_step_delay()
            try:
                from media_importer.api import globals as _api_globals
                from media_importer.features.scraping import get_dimensions_for_provider
                conn = _api_globals._global_task_manager.conn if _api_globals._global_task_manager else None
                if conn:
                    dim_configs = get_dimensions_for_provider(conn, cached_provider.provider_type)
                    dim_mappings = cached_provider.map_dimensions(dim_configs, cached_details)
                    derived_dims = {dm.name: {"value": dm.value, "source": dm.source} for dm in dim_mappings}
                    # 补充无 provider_mappings 的基础维度（如 media_type）
                    media_type = scrape_result.get("media_type", "")
                    if media_type and "media_type" not in derived_dims:
                        derived_dims["media_type"] = {"value": media_type, "source": "file"}
                    scrape_result["dimensions"] = derived_dims
                    _preview_add_step(job, "scrape", "维度推导", "done",
                                      f"推导出 {len(derived_dims)} 个维度",
                                      {"dimensions": derived_dims})
                else:
                    _preview_add_step(job, "scrape", "维度推导", "done", "无 DB 连接，跳过维度推导")
            except Exception as e:
                if logger:
                    logger.warning(f"[scrape_preview_job] 维度推导失败: {e}")
                _preview_add_step(job, "scrape", "维度推导", "done", f"维度推导失败: {e}")

        _preview_add_step(job, "classify", "入库路径预估", "running", "正在计算入库路径...")
        _preview_step_delay()
        import_path = ""
        used_fallback = False
        matched_rule = None
        try:
            from media_importer.features.import_flow.services.classification_rules import classify
            rules = (config or {}).get("classification", {}).get("rules", [])
            if not rules:
                rules = (config or {}).get("path_rules", [])
            if rules:
                import_path = classify(scrape_result, rules, None)
            if not import_path:
                import_path = (config or {}).get("fallback_dir", "")
                used_fallback = bool(import_path)
        except Exception as e:
            if logger:
                logger.warning(f"[scrape_preview_job] 入库路径计算失败: {e}")

        _preview_add_step(job, "classify", "入库路径预估", "done",
                          f"入库路径={import_path or '(未命中)'}",
                          {"import_path": import_path, "used_fallback": used_fallback})

        scrape_elapsed = round(time.time() - job["started_at"], 2)
        job["status"] = "done"
        job["result"] = {
            "filename": filename,
            "clean_result": {
                "clean_title": clean_result.clean_title,
                "year": clean_result.year,
                "season": clean_result.season,
                "episode": clean_result.episode,
                "method": clean_result.method,
                "removed_items": clean_result.removed_items,
            },
            "scrape_result": scrape_result,
            "scrape_elapsed": scrape_elapsed,
            "match_result": match_dict,
            "import_path": {
                "import_path": import_path,
                "used_fallback": used_fallback,
                "matched_rule": matched_rule,
            },
        }
        job["updated_at"] = time.time()

        if logger:
            logger.info(f"[scrape_preview_job] 完成: {job_id}, {scrape_elapsed}s, match_level={match_level}")

    except Exception as e:
        if logger:
            logger.error(f"[scrape_preview_job] 异常: {e}", exc_info=True)
        job["status"] = "failed"
        job["error"] = str(e)
        job["updated_at"] = time.time()
        _preview_add_step(job, "failed", "模拟测试失败", "failed",
                          str(e)[:200])
