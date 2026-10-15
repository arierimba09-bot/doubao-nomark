import os
import httpx
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, HttpUrl

from doubao_parser.image import doubao_image_parse, qianwen_image_parse
from doubao_parser.video import doubao_video_parse, yunque_video_parse

app = FastAPI(title="无印豆包 API", description="从豆包|千问对话链接中提取图片和视频资源", version="1.0.9")

ALLOWED_DOUBAO_HOSTS = {"doubao.com", "www.doubao.com", "dola.com", "www.dola.com"}
ALLOWED_QIANWEN_HOSTS = {"qianwen.com", "www.qianwen.com"}


def _host_matches(url: str, allowed_hosts: set[str]) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return hostname in allowed_hosts or any(hostname.endswith(f".{host}") for host in allowed_hosts)


if os.path.exists("icons"):
    app.mount("/icons", StaticFiles(directory="icons"), name="icons")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class DouBaoRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"url": "https://www.doubao.com/thread/aef4c7a4c78c2", "return_raw": False}}
    )

    url: HttpUrl
    return_raw: bool = False


class DouBaoResponse(BaseModel):
    success: bool
    image_count: int
    images: list[dict]


class VideoRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"url": "https://www.doubao.com/thread/xxxxxx", "return_raw": False}}
    )

    url: HttpUrl
    return_raw: bool = False


class VideoResponse(BaseModel):
    success: bool
    video_count: int
    videos: list[dict]


@app.get("/", summary="首页", include_in_schema=False)
async def root():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {
        "message": "Doubao Parser - Extract images and videos from Doubao links",
        "docs": "/docs",
        "version": "1.0.4",
    }


@app.post("/parse", summary="解析豆包|千问对话图片")
async def parse_doubao(request: DouBaoRequest):
    try:
        url_str = str(request.url)
        if _host_matches(url_str, ALLOWED_DOUBAO_HOSTS):
            result = await doubao_image_parse(url_str, return_raw=request.return_raw)
        elif _host_matches(url_str, ALLOWED_QIANWEN_HOSTS):
            result = await qianwen_image_parse(url_str, return_raw=request.return_raw)
        else:
            raise HTTPException(status_code=400, detail="不支持的链接域名")

        if request.return_raw:
            return {"success": True, "data": result}

        return DouBaoResponse(success=True, image_count=len(result), images=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Exception: {e}")
        raise HTTPException(status_code=500, detail="图片解析失败，请检查链接是否正确")


@app.get("/parse", summary="解析豆包|千问对话图片(GET)")
async def parse_doubao_get(url: str, return_raw: bool = False):
    try:
        if _host_matches(url, ALLOWED_DOUBAO_HOSTS):
            result = await doubao_image_parse(url, return_raw=return_raw)
        elif _host_matches(url, ALLOWED_QIANWEN_HOSTS):
            result = await qianwen_image_parse(url, return_raw=return_raw)
        else:
            raise HTTPException(status_code=400, detail="不支持的链接域名")

        if return_raw:
            return {"success": True, "data": result}

        return DouBaoResponse(success=True, image_count=len(result), images=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Exception: {e}")
        raise HTTPException(status_code=500, detail="图片解析失败，请检查链接是否正确")




@app.get("/debug-dola")
async def debug_dola():
    from doubao_parser.video import DOUBAO_HEADERS, _extract_fallback_apis
    url = "https://www.dola.com/thread/xZEnUfMdaJhZydLoV"
    result = {"stage": "start"}
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            result["stage"] = "fetch_page"
            page = await client.get(url, headers=DOUBAO_HEADERS)
            result["http_status"] = page.status_code
            result["final_host"] = page.url.host
            result["html_length"] = len(page.text)
            result["html_start"] = " ".join(page.text[:1200].split())
            result["html_end"] = " ".join(page.text[-500:].split())
            html_lower = page.text.lower()
            result["markers"] = {
                "fallback_api": "fallback_api" in html_lower,
                "data_fn_args": "data-fn-args" in html_lower,
                "modern_router": "modern-run-router-data-fn" in html_lower,
                "video_info": "video_info" in html_lower,
                "captcha": "captcha" in html_lower,
            }
            result["content_type"] = page.headers.get("content-type", "")
            result["stage"] = "extract_apis"
            apis = _extract_fallback_apis(page.text)
            result["api_count"] = len(apis)
            result["stage"] = "complete"
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error"] = str(exc)[:300]
    return result

@app.post("/parse-video", summary="解析豆包|云雀视频")
async def parse_video(request: VideoRequest):
    try:
        url_str = str(request.url)
        if _host_matches(url_str, ALLOWED_DOUBAO_HOSTS):
            video_data = await doubao_video_parse(url_str, return_raw=request.return_raw)
        elif _host_matches(url_str, ALLOWED_QIANWEN_HOSTS):
            video_data = await yunque_video_parse(url_str, return_raw=request.return_raw)
        else:
            raise HTTPException(status_code=400, detail="不支持的链接域名")

        if request.return_raw:
            return {"success": True, "data": video_data}

        return VideoResponse(success=True, video_count=len(video_data), videos=video_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Exception: {e}")
        raise HTTPException(status_code=500, detail="视频解析失败，请检查链接是否正确")


@app.get("/parse-video", summary="解析豆包|云雀视频(GET)")
async def parse_video_get(url: str, return_raw: bool = False):
    try:
        if _host_matches(url, ALLOWED_DOUBAO_HOSTS):
            video_data = await doubao_video_parse(url, return_raw=return_raw)
        elif _host_matches(url, ALLOWED_QIANWEN_HOSTS):
            video_data = await yunque_video_parse(url, return_raw=return_raw)
        else:
            raise HTTPException(status_code=400, detail="不支持的链接域名")
        if return_raw:
            return {"success": True, "data": video_data}

        return VideoResponse(success=True, video_count=len(video_data), videos=video_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Exception: {e}")
        raise HTTPException(status_code=500, detail="视频解析失败，请检查链接是否正确")



@app.get("/download-video")
async def download_video(url: HttpUrl):
    source = str(url)
    parsed = urlparse(source)
    host = (parsed.hostname or "").lower()

    allowed_hosts = (
        host == "dola.com"
        or host.endswith(".dola.com")
        or host == "byteimg.com"
        or host.endswith(".byteimg.com")
    )

    if parsed.scheme not in ("https", "http") or not allowed_hosts:
        raise HTTPException(
            status_code=400,
            detail="URL video bukan dari domain Dola yang diizinkan."
        )

    client = httpx.AsyncClient(
        timeout=90,
        follow_redirects=False
    )

    try:
        request = client.build_request(
            "GET",
            source,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        response = await client.send(request, stream=True)

        if response.status_code >= 300:
            await response.aclose()
            await client.aclose()
            raise HTTPException(
                status_code=502,
                detail="Sumber video gagal diakses atau mengalihkan URL."
            )

        content_type = response.headers.get(
            "content-type", ""
        ).lower()

        if "text/html" in content_type or "application/json" in content_type:
            await response.aclose()
            await client.aclose()
            raise HTTPException(
                status_code=502,
                detail="Sumber mengembalikan halaman, bukan video."
            )

        async def stream_video():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        return StreamingResponse(
            stream_video(),
            media_type="video/mp4",
            headers={
                "Content-Disposition":
                    'attachment; filename="CreatorTools-Video.mp4"',
                "X-Content-Type-Options": "nosniff"
            },
            background=BackgroundTask(client.aclose)
        )

    except HTTPException:
        raise
    except Exception as exc:
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail="Gagal mengambil video sumber."
        ) from exc

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
