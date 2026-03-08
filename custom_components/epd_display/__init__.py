"""The EPD Display integration."""

import json
import logging
import os
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.template import Template
from homeassistant.components.http import HomeAssistantView, StaticPathConfig

from .api import EpdApiClient, EpdBusyError
from .const import (
    DOMAIN, CONF_HOST, CONF_PORT, CONF_DEVICE_NAME,
    CONF_CANVAS, CONF_DRIVER, CONF_DITHER_MODE,
    CONF_CONTRAST, CONF_DITHER_STRENGTH,
    DEFAULT_CANVAS, DEFAULT_DRIVER, DEFAULT_DITHER_MODE,
    DEFAULT_CONTRAST, DEFAULT_DITHER_STRENGTH,
    SERVICE_CONNECT, SERVICE_DISCONNECT, SERVICE_CLEAR,
    SERVICE_REFRESH, SERVICE_SLEEP,
    SERVICE_SYNC_TIME, SERVICE_SYS_RESET,
    SERVICE_DISPLAY_IMAGE, SERVICE_DISPLAY_URL,
    SERVICE_GENERATE_IMAGE, SERVICE_RENDER_TEMPLATE,
    ATTR_IMAGE_PATH, ATTR_IMAGE_URL,
    ATTR_CANVAS, ATTR_DRIVER, ATTR_DITHER_MODE,
    ATTR_CONTRAST, ATTR_DITHER_STRENGTH,
    ATTR_CLOCK_MODE,
    ATTR_WIDTH, ATTR_HEIGHT,
    ATTR_BACKGROUND_COLOR, ATTR_BACKGROUND_IMAGE,
    ATTR_ELEMENTS, ATTR_OUTPUT_FILENAME,
    ATTR_TEMPLATE_NAME, ATTR_SEND_AFTER,
    CANVAS_OPTIONS, DITHER_MODES,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "button"]


# ══════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════

def _get_client(hass):
    for entry_data in hass.data.get(DOMAIN, {}).values():
        return entry_data["client"]
    raise ValueError("No EPD Display configured")


def _get_config(hass):
    for entry_data in hass.data.get(DOMAIN, {}).values():
        return entry_data["config"]
    return {}


def _resolve_elements(hass, elements: list[dict]) -> tuple[dict, dict]:
    """Walk elements, resolve entity_text and computed_text.

    Returns (entity_states, computed_results) dicts.
    """
    entity_states: dict[str, str] = {}
    computed_results: dict[str, str] = {}

    for idx, elem in enumerate(elements):
        etype = elem.get("type")

        if etype == "entity_text":
            eid = elem.get("entity_id", "")
            if eid:
                s = hass.states.get(eid)
                entity_states[eid] = s.state if s else "N/A"

        elif etype == "computed_text":
            tpl_str = elem.get("template", "")
            if tpl_str:
                try:
                    tpl = Template(tpl_str, hass)
                    tpl.hass = hass
                    computed_results[str(idx)] = tpl.async_render()
                except Exception as err:
                    _LOGGER.warning("Template render error [%d]: %s", idx, err)
                    computed_results[str(idx)] = f"ERR: {err}"

    return entity_states, computed_results


# ══════════════════════════════════════════════════════════
# HTTP Views
# ══════════════════════════════════════════════════════════

class EpdUploadView(HomeAssistantView):
    url = "/api/epd_display/upload"
    name = "api:epd_display:upload"
    requires_auth = True

    async def post(self, request):
        from aiohttp import web
        hass = request.app["hass"]
        reader = await request.multipart()
        image_data = None; filename = "upload.png"
        canvas = driver = dither_mode = None
        contrast = 1.0; dither_strength = 1.0
        while True:
            part = await reader.next()
            if part is None: break
            if part.name == "image":
                image_data = await part.read(); filename = part.filename or filename
            elif part.name == "canvas": canvas = (await part.read()).decode()
            elif part.name == "driver": driver = (await part.read()).decode()
            elif part.name == "dither_mode": dither_mode = (await part.read()).decode()
            elif part.name == "contrast": contrast = float((await part.read()).decode())
            elif part.name == "dither_strength": dither_strength = float((await part.read()).decode())
        if not image_data:
            return web.json_response({"error": "No image"}, status=400)
        try:
            client = _get_client(hass); cfg = _get_config(hass)
            result = await client.async_display_image_bytes(
                image_bytes=image_data, filename=filename,
                canvas=canvas or cfg.get(CONF_CANVAS, DEFAULT_CANVAS),
                driver=driver or cfg.get(CONF_DRIVER, DEFAULT_DRIVER),
                dither_mode=dither_mode or cfg.get(CONF_DITHER_MODE, DEFAULT_DITHER_MODE),
                contrast=contrast, dither_strength=dither_strength,
            )
            return web.json_response({"status": "ok", "result": result})
        except Exception as err:
            return web.json_response({"error": str(err)}, status=500)


class EpdDisplayUrlView(HomeAssistantView):
    url = "/api/epd_display/display_url"
    name = "api:epd_display:display_url"
    requires_auth = True

    async def post(self, request):
        from aiohttp import web
        hass = request.app["hass"]; data = await request.json()
        url_val = data.get("image_url")
        if not url_val:
            return web.json_response({"error": "No image_url"}, status=400)
        try:
            client = _get_client(hass); cfg = _get_config(hass)
            result = await client.async_display_url(
                image_url=url_val,
                canvas=data.get("canvas") or cfg.get(CONF_CANVAS, DEFAULT_CANVAS),
                driver=data.get("driver") or cfg.get(CONF_DRIVER, DEFAULT_DRIVER),
                dither_mode=data.get("dither_mode") or cfg.get(CONF_DITHER_MODE, DEFAULT_DITHER_MODE),
                contrast=float(data.get("contrast", 1.0)),
                dither_strength=float(data.get("dither_strength", 1.0)),
            )
            return web.json_response({"status": "ok", "result": result})
        except Exception as err:
            return web.json_response({"error": str(err)}, status=500)


class EpdEntitiesView(HomeAssistantView):
    url = "/api/epd_display/entities"
    name = "api:epd_display:entities"
    requires_auth = True

    async def get(self, request):
        from aiohttp import web
        hass = request.app["hass"]
        entities = [{
            "entity_id": s.entity_id,
            "state": s.state,
            "name": s.attributes.get("friendly_name", s.entity_id),
            "unit": s.attributes.get("unit_of_measurement", ""),
            "device_class": s.attributes.get("device_class", ""),
        } for s in hass.states.async_all()]
        return web.json_response(entities)


class EpdConfigView(HomeAssistantView):
    url = "/api/epd_display/config"
    name = "api:epd_display:config"
    requires_auth = True

    async def get(self, request):
        from aiohttp import web
        hass = request.app["hass"]; cfg = _get_config(hass)
        return web.json_response({
            "canvas_options": CANVAS_OPTIONS,
            "dither_modes": DITHER_MODES,
            "defaults": {
                "canvas": cfg.get(CONF_CANVAS, DEFAULT_CANVAS),
                "driver": cfg.get(CONF_DRIVER, DEFAULT_DRIVER),
                "dither_mode": cfg.get(CONF_DITHER_MODE, DEFAULT_DITHER_MODE),
                "contrast": cfg.get(CONF_CONTRAST, DEFAULT_CONTRAST),
                "dither_strength": cfg.get(CONF_DITHER_STRENGTH, DEFAULT_DITHER_STRENGTH),
            },
        })


class EpdMediaListView(HomeAssistantView):
    """List image files available on the HA server for use as backgrounds.

    Scans the following directories (relative to HA config root):
      • www/           (served as /local/…)
      • epd_images/    (generated by this integration)
      • epd_templates/ (skipped – JSON only)

    Query params
    ------------
    subdir  : optional extra sub-path inside www/ to browse
    search  : optional filename filter (case-insensitive substring)
    """

    url  = "/api/epd_display/media_list"
    name = "api:epd_display:media_list"
    requires_auth = True

    _IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

    async def get(self, request):
        from aiohttp import web
        import os

        hass    = request.app["hass"]
        subdir  = request.query.get("subdir", "").strip("/")
        search  = request.query.get("search", "").lower()
        cfg_dir = hass.config.path()

        # Directories to scan: (display_root, fs_root, url_prefix)
        scan_dirs = [
            ("www" + (f"/{subdir}" if subdir else ""),
             os.path.join(cfg_dir, "www", subdir) if subdir else os.path.join(cfg_dir, "www"),
             "/local/" + (subdir + "/" if subdir else "")),
            ("epd_images",
             os.path.join(cfg_dir, "epd_images"),
             None),   # served via proxy
        ]

        files  = []
        dirs   = []

        for disp_root, fs_root, url_prefix in scan_dirs:
            if not os.path.isdir(fs_root):
                continue
            try:
                entries = sorted(os.scandir(fs_root), key=lambda e: (not e.is_dir(), e.name.lower()))
            except PermissionError:
                continue
            for entry in entries:
                name = entry.name
                if name.startswith("."):
                    continue
                if entry.is_dir():
                    dirs.append({
                        "name": name,
                        "path": os.path.join(disp_root, name),
                        "type": "dir",
                    })
                elif entry.is_file():
                    ext = os.path.splitext(name)[1].lower()
                    if ext not in self._IMG_EXTS:
                        continue
                    if search and search not in name.lower():
                        continue
                    rel_path = os.path.relpath(entry.path, cfg_dir)
                    # build a browseable URL: www files can use /local/, others need proxy
                    if url_prefix:
                        preview_url = url_prefix + name
                    else:
                        preview_url = f"/api/epd_display/media_proxy?path={rel_path}"
                    files.append({
                        "name": name,
                        "path": rel_path,          # relative to config dir
                        "abs_path": entry.path,    # absolute FS path (for background_image)
                        "size": entry.stat().st_size,
                        "preview_url": preview_url,
                        "source": disp_root,
                    })

        return web.json_response({
            "files": files,
            "dirs":  dirs,
            "current": subdir or "",
        })


class EpdMediaProxyView(HomeAssistantView):
    """Serve a HA-local image file to the browser (used for epd_images preview).

    Query params
    ------------
    path : path relative to HA config dir  e.g. "epd_images/foo.png"
    """

    url  = "/api/epd_display/media_proxy"
    name = "api:epd_display:media_proxy"
    requires_auth = True

    _IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    _MIME = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",  ".gif": "image/gif",
        ".webp": "image/webp", ".bmp": "image/bmp",
    }
    # Only allow files inside these safe sub-directories
    _SAFE_ROOTS = ("www", "epd_images", "epd_templates")

    async def get(self, request):
        from aiohttp import web
        import os

        hass     = request.app["hass"]
        rel_path = request.query.get("path", "").strip("/").replace("..", "")

        # safety: must start with a known safe root
        first_part = rel_path.split("/")[0] if rel_path else ""
        if first_part not in self._SAFE_ROOTS:
            return web.Response(status=403, text="Forbidden")

        ext = os.path.splitext(rel_path)[1].lower()
        if ext not in self._IMG_EXTS:
            return web.Response(status=400, text="Not an image")

        abs_path = hass.config.path(rel_path)
        if not os.path.isfile(abs_path):
            return web.Response(status=404, text="Not found")

        mime = self._MIME.get(ext, "application/octet-stream")
        try:
            with open(abs_path, "rb") as f:
                data = f.read()
            return web.Response(body=data, content_type=mime,
                                headers={"Cache-Control": "max-age=60"})
        except Exception as err:
            return web.Response(status=500, text=str(err))


async def _fetch_calendar_events(hass, entity_ids: list, start_dt, end_dt) -> list:
    """Fetch events from HA calendar entities for the given time range."""
    from homeassistant.components.calendar import async_get_events
    events = []
    for eid in entity_ids:
        try:
            entity_events = await async_get_events(hass, eid, start_dt, end_dt)
            for ev in entity_events:
                events.append({
                    "summary": ev.summary or "",
                    "start": ev.start.isoformat() if hasattr(ev.start, "isoformat") else str(ev.start),
                    "end": ev.end.isoformat() if hasattr(ev.end, "isoformat") else str(ev.end),
                    "all_day": getattr(ev, "all_day", False),
                })
        except Exception as err:
            _LOGGER.warning("Failed to fetch calendar events for %s: %s", eid, err)
    return events


async def _resolve_calendar_elements(hass, elements: list, computed_results: dict) -> None:
    """For each calendar element, fetch events and store in computed_results."""
    import datetime
    for idx, elem in enumerate(elements):
        if elem.get("type") != "calendar":
            continue
        entity_ids = elem.get("calendar_entities", [])
        if not entity_ids:
            continue
        year = elem.get("year") or datetime.date.today().year
        month = elem.get("month") or datetime.date.today().month
        start_dt = datetime.datetime(int(year), int(month), 1, tzinfo=datetime.timezone.utc)
        # last day of month
        if int(month) == 12:
            end_dt = datetime.datetime(int(year) + 1, 1, 1, tzinfo=datetime.timezone.utc)
        else:
            end_dt = datetime.datetime(int(year), int(month) + 1, 1, tzinfo=datetime.timezone.utc)
        events = await _fetch_calendar_events(hass, entity_ids, start_dt, end_dt)
        computed_results[f"_cal_{idx}"] = events


class EpdCalendarView(HomeAssistantView):
    """GET /api/epd_display/calendar_events?entity_id=...&year=...&month=..."""
    url = "/api/epd_display/calendar_events"
    name = "api:epd_display:calendar_events"
    requires_auth = True

    async def get(self, request):
        from aiohttp import web
        import datetime
        hass = request.app["hass"]
        entity_ids = request.rel_url.query.getall("entity_id", [])
        year = int(request.rel_url.query.get("year", datetime.date.today().year))
        month = int(request.rel_url.query.get("month", datetime.date.today().month))
        if not entity_ids:
            return web.json_response({"error": "No entity_id provided"}, status=400)
        start_dt = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
        end_dt = datetime.datetime(year + (1 if month == 12 else 0),
                                   1 if month == 12 else month + 1, 1,
                                   tzinfo=datetime.timezone.utc)
        events = await _fetch_calendar_events(hass, entity_ids, start_dt, end_dt)
        return web.json_response({"events": events, "year": year, "month": month})


class EpdGenerateView(HomeAssistantView):
    url = "/api/epd_display/generate"
    name = "api:epd_display:generate"
    requires_auth = True

    async def post(self, request):
        from aiohttp import web
        from .image_editor import generate_image
        hass = request.app["hass"]; data = await request.json()
        width = int(data.get("width", 800))
        height = int(data.get("height", 480))
        elements = data.get("elements", [])
        entity_states, computed_results = _resolve_elements(hass, elements)
        # resolve calendar elements (async)
        await _resolve_calendar_elements(hass, elements, computed_results)
        try:
            path = await hass.async_add_executor_job(
                generate_image, hass.config.path(),
                width, height,
                data.get("background_color", "white"),
                data.get("background_image"),
                elements,
                data.get("output_filename", "epd_editor_output.png"),
                entity_states, computed_results,
            )
            return web.json_response({"status": "ok", "path": path})
        except Exception as err:
            return web.json_response({"error": str(err)}, status=500)


# ── Template CRUD views ──────────────────────────────────

class EpdTemplateListView(HomeAssistantView):
    url = "/api/epd_display/templates"
    name = "api:epd_display:templates"
    requires_auth = True

    async def get(self, request):
        from aiohttp import web
        from .image_editor import list_templates
        hass = request.app["hass"]
        names = await hass.async_add_executor_job(
            list_templates, hass.config.path()
        )
        return web.json_response({"templates": names})


class EpdTemplateSaveView(HomeAssistantView):
    url = "/api/epd_display/templates/{name}"
    name = "api:epd_display:templates:save"
    requires_auth = True

    async def put(self, request, name):
        from aiohttp import web
        from .image_editor import save_template
        hass = request.app["hass"]; data = await request.json()
        path = await hass.async_add_executor_job(
            save_template, hass.config.path(), name, data
        )
        return web.json_response({"status": "ok", "path": path})

    async def get(self, request, name):
        from aiohttp import web
        from .image_editor import load_template
        hass = request.app["hass"]
        tpl = await hass.async_add_executor_job(
            load_template, hass.config.path(), name
        )
        if tpl is None:
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response(tpl)

    async def delete(self, request, name):
        from aiohttp import web
        from .image_editor import delete_template
        hass = request.app["hass"]
        ok = await hass.async_add_executor_job(
            delete_template, hass.config.path(), name
        )
        return web.json_response({"status": "ok" if ok else "not_found"})


class EpdTemplatePreviewView(HomeAssistantView):
    """Evaluate a Jinja2 template string and return the result."""
    url = "/api/epd_display/template_preview"
    name = "api:epd_display:template_preview"
    requires_auth = True

    async def post(self, request):
        from aiohttp import web
        hass = request.app["hass"]; data = await request.json()
        tpl_str = data.get("template", "")
        try:
            tpl = Template(tpl_str, hass)
            tpl.hass = hass
            result = tpl.async_render()
            return web.json_response({"result": str(result)})
        except Exception as err:
            return web.json_response({"error": str(err)}, status=400)



class EpdParseYamlView(HomeAssistantView):
    """Parse a YAML string and return JSON — used by the editor frontend."""
    url = "/api/epd_display/parse_yaml"
    name = "api:epd_display:parse_yaml"
    requires_auth = True

    async def post(self, request):
        from aiohttp import web
        import yaml as _yaml
        data = await request.json()
        yaml_str = data.get("yaml", "")
        try:
            parsed = _yaml.safe_load(yaml_str)
            if not isinstance(parsed, dict):
                return web.json_response({"error": "YAML 根节点必须是字典"}, status=400)
            return web.json_response({"result": parsed})
        except Exception as err:
            return web.json_response({"error": str(err)}, status=400)


# ══════════════════════════════════════════════════════════
# Entry setup
# ══════════════════════════════════════════════════════════

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    host = entry.data[CONF_HOST]; port = entry.data[CONF_PORT]
    session = async_get_clientsession(hass)
    client = EpdApiClient(host, port, session)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"client": client, "config": entry.data}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)

    # HTTP views
    for view_cls in (
        EpdUploadView, EpdDisplayUrlView, EpdEntitiesView,
        EpdConfigView, EpdMediaListView, EpdMediaProxyView, EpdGenerateView,
        EpdCalendarView,
        EpdTemplateListView, EpdTemplateSaveView, EpdTemplatePreviewView, EpdParseYamlView,
    ):
        hass.http.register_view(view_cls())

    # Static editor page
    frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
    await hass.http.async_register_static_paths([
        StaticPathConfig("/epd_display/editor", os.path.join(frontend_dir, "editor.html"), False),
    ])
    _LOGGER.info("EPD editor at /epd_display/editor")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return ok


# ══════════════════════════════════════════════════════════
# Service registration
# ══════════════════════════════════════════════════════════

def _register_services(hass):
    if hass.services.has_service(DOMAIN, SERVICE_CONNECT):
        return

    # ── Basic device control ──────────────────────────────

    async def handle_connect(call):
        client = _get_client(hass); cfg = _get_config(hass)
        name = call.data.get("device_name", cfg.get(CONF_DEVICE_NAME))
        try: await client.async_connect(name)
        except EpdBusyError as e: _LOGGER.warning("EPD connect 被拒绝（设备忙）: %s", e)
        except Exception as e: _LOGGER.error("EPD connect: %s", e)

    async def handle_disconnect(call):
        try: await _get_client(hass).async_disconnect()
        except EpdBusyError as e: _LOGGER.warning("EPD disconnect 被拒绝（设备忙）: %s", e)
        except Exception as e: _LOGGER.error("EPD disconnect: %s", e)

    async def handle_clear(call):
        try: await _get_client(hass).async_clear()
        except EpdBusyError as e: _LOGGER.warning("EPD clear 被拒绝（设备忙）: %s", e)
        except Exception as e: _LOGGER.error("EPD clear: %s", e)

    async def handle_refresh(call):
        try: await _get_client(hass).async_refresh()
        except EpdBusyError as e: _LOGGER.warning("EPD refresh 被拒绝（设备忙）: %s", e)
        except Exception as e: _LOGGER.error("EPD refresh: %s", e)

    async def handle_sleep(call):
        try: await _get_client(hass).async_sleep()
        except EpdBusyError as e: _LOGGER.warning("EPD sleep 被拒绝（设备忙）: %s", e)
        except Exception as e: _LOGGER.error("EPD sleep: %s", e)

    async def handle_sync_time(call):
        """同步时间并启动内置时钟/日历。mode=1 局刷时钟, mode=2 全刷日历。"""
        try:
            mode = int(call.data.get(ATTR_CLOCK_MODE, 1))
            await _get_client(hass).async_sync_time(mode=mode)
        except EpdBusyError as e: _LOGGER.warning("EPD sync_time 被拒绝（设备忙）: %s", e)
        except Exception as e: _LOGGER.error("EPD sync_time: %s", e)

    async def handle_sys_reset(call):
        """系统重置"""
        try: await _get_client(hass).async_sys_reset()
        except EpdBusyError as e: _LOGGER.warning("EPD sys_reset 被拒绝（设备忙）: %s", e)
        except Exception as e: _LOGGER.error("EPD sys_reset: %s", e)

    # ── Image services ────────────────────────────────────

    async def handle_display_image(call):
        client = _get_client(hass); cfg = _get_config(hass)
        try:
            await client.async_display_image(
                image_path=call.data[ATTR_IMAGE_PATH],
                canvas=call.data.get(ATTR_CANVAS, cfg.get(CONF_CANVAS, DEFAULT_CANVAS)),
                driver=call.data.get(ATTR_DRIVER, cfg.get(CONF_DRIVER, DEFAULT_DRIVER)),
                dither_mode=call.data.get(ATTR_DITHER_MODE, cfg.get(CONF_DITHER_MODE, DEFAULT_DITHER_MODE)),
                contrast=call.data.get(ATTR_CONTRAST, cfg.get(CONF_CONTRAST, DEFAULT_CONTRAST)),
                dither_strength=call.data.get(ATTR_DITHER_STRENGTH, cfg.get(CONF_DITHER_STRENGTH, DEFAULT_DITHER_STRENGTH)),
            )
        except Exception as e: _LOGGER.error("display_image: %s", e)

    async def handle_display_url(call):
        client = _get_client(hass); cfg = _get_config(hass)
        try:
            await client.async_display_url(
                image_url=call.data[ATTR_IMAGE_URL],
                canvas=call.data.get(ATTR_CANVAS, cfg.get(CONF_CANVAS, DEFAULT_CANVAS)),
                driver=call.data.get(ATTR_DRIVER, cfg.get(CONF_DRIVER, DEFAULT_DRIVER)),
                dither_mode=call.data.get(ATTR_DITHER_MODE, cfg.get(CONF_DITHER_MODE, DEFAULT_DITHER_MODE)),
                contrast=call.data.get(ATTR_CONTRAST, cfg.get(CONF_CONTRAST, DEFAULT_CONTRAST)),
                dither_strength=call.data.get(ATTR_DITHER_STRENGTH, cfg.get(CONF_DITHER_STRENGTH, DEFAULT_DITHER_STRENGTH)),
            )
        except Exception as e: _LOGGER.error("display_url: %s", e)

    # ── generate_image ────────────────────────────────────

    async def handle_generate_image(call: ServiceCall):
        from .image_editor import generate_image
        elements = call.data.get(ATTR_ELEMENTS, [])
        entity_states, computed_results = _resolve_elements(hass, elements)
        await _resolve_calendar_elements(hass, elements, computed_results)
        try:
            path = await hass.async_add_executor_job(
                generate_image, hass.config.path(),
                call.data[ATTR_WIDTH], call.data[ATTR_HEIGHT],
                call.data.get(ATTR_BACKGROUND_COLOR, "white"),
                call.data.get(ATTR_BACKGROUND_IMAGE),
                elements,
                call.data.get(ATTR_OUTPUT_FILENAME, "epd_editor_output.png"),
                entity_states, computed_results,
            )
            _LOGGER.info("generate_image -> %s", path)
        except Exception as e: _LOGGER.error("generate_image: %s", e)

    # ── render_template  ──────────────────────────────────
    # Loads a saved template, resolves all dynamic elements,
    # generates the image, and optionally sends it to the EPD.

    async def handle_render_template(call: ServiceCall):
        from .image_editor import load_template, generate_image

        name = call.data[ATTR_TEMPLATE_NAME]
        send_after = call.data.get(ATTR_SEND_AFTER, False)

        tpl = await hass.async_add_executor_job(
            load_template, hass.config.path(), name,
        )
        if not tpl:
            _LOGGER.error("Template '%s' not found", name)
            return

        elements = tpl.get("elements", [])
        entity_states, computed_results = _resolve_elements(hass, elements)
        await _resolve_calendar_elements(hass, elements, computed_results)

        filename = tpl.get("output_filename", f"tpl_{name}.png")
        try:
            path = await hass.async_add_executor_job(
                generate_image, hass.config.path(),
                tpl.get("width", 800), tpl.get("height", 480),
                tpl.get("background_color", "white"),
                tpl.get("background_image"),
                elements, filename,
                entity_states, computed_results,
            )
            _LOGGER.info("render_template '%s' -> %s", name, path)
        except Exception as e:
            _LOGGER.error("render_template '%s' failed: %s", name, e)
            return

        if send_after:
            try:
                client = _get_client(hass); cfg = _get_config(hass)
                await client.async_display_image(
                    image_path=path,
                    canvas=cfg.get(CONF_CANVAS, DEFAULT_CANVAS),
                    driver=cfg.get(CONF_DRIVER, DEFAULT_DRIVER),
                    dither_mode=cfg.get(CONF_DITHER_MODE, DEFAULT_DITHER_MODE),
                    contrast=cfg.get(CONF_CONTRAST, DEFAULT_CONTRAST),
                    dither_strength=cfg.get(CONF_DITHER_STRENGTH, DEFAULT_DITHER_STRENGTH),
                )
                _LOGGER.info("render_template '%s' sent to EPD", name)
            except Exception as e:
                _LOGGER.error("render_template send failed: %s", e)

    # ── Register all services ─────────────────────────────

    hass.services.async_register(DOMAIN, SERVICE_CONNECT, handle_connect,
        schema=vol.Schema({vol.Optional("device_name"): str}))
    hass.services.async_register(DOMAIN, SERVICE_DISCONNECT, handle_disconnect)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR, handle_clear)
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, handle_refresh)
    hass.services.async_register(DOMAIN, SERVICE_SLEEP, handle_sleep)
    hass.services.async_register(DOMAIN, SERVICE_SYNC_TIME, handle_sync_time,
        schema=vol.Schema({vol.Optional(ATTR_CLOCK_MODE, default=1): vol.Coerce(int)}))
    hass.services.async_register(DOMAIN, SERVICE_SYS_RESET, handle_sys_reset)

    _img_schema_opts = {
        vol.Optional(ATTR_CANVAS): str,
        vol.Optional(ATTR_DRIVER): str,
        vol.Optional(ATTR_DITHER_MODE): str,
        vol.Optional(ATTR_CONTRAST): vol.Coerce(float),
        vol.Optional(ATTR_DITHER_STRENGTH): vol.Coerce(float),
    }
    hass.services.async_register(DOMAIN, SERVICE_DISPLAY_IMAGE, handle_display_image,
        schema=vol.Schema({vol.Required(ATTR_IMAGE_PATH): str, **_img_schema_opts}))
    hass.services.async_register(DOMAIN, SERVICE_DISPLAY_URL, handle_display_url,
        schema=vol.Schema({vol.Required(ATTR_IMAGE_URL): str, **_img_schema_opts}))

    hass.services.async_register(DOMAIN, SERVICE_GENERATE_IMAGE, handle_generate_image,
        schema=vol.Schema({
            vol.Required(ATTR_WIDTH): vol.Coerce(int),
            vol.Required(ATTR_HEIGHT): vol.Coerce(int),
            vol.Optional(ATTR_BACKGROUND_COLOR, default="white"): str,
            vol.Optional(ATTR_BACKGROUND_IMAGE): str,
            vol.Optional(ATTR_ELEMENTS, default=[]): list,
            vol.Optional(ATTR_OUTPUT_FILENAME, default="epd_editor_output.png"): str,
        }))

    hass.services.async_register(DOMAIN, SERVICE_RENDER_TEMPLATE, handle_render_template,
        schema=vol.Schema({
            vol.Required(ATTR_TEMPLATE_NAME): str,
            vol.Optional(ATTR_SEND_AFTER, default=False): bool,
        }))

    _LOGGER.info("EPD Display services registered")
