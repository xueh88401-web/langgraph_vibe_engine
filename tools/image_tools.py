"""
图像工具 — upload_image, text2img, img2img, finish_image_generation

- upload_image: 用户上传图片 → COS → 返回公网 URL
- text2img / img2img: 调用火山引擎豆包 Seedream 3.0 API
- finish_image_generation: ImageGeneration SubAgent 终止工具

对应原项目:
- tools/imagegeneration_text2img.py (Text2ImageGenerator)
- tools/imagegeneration_img2img.py (Image2ImageGenerator)
- tools/imagegeneration_base.py (COSUploader)
"""

import os
import uuid
import base64
import logging
import requests
from pathlib import Path
from langchain_core.tools import tool

logger = logging.getLogger("ImageTools")
logger.setLevel(logging.INFO)

# ── API 配置 ──────────────────────────────────────────────
DOUBAO_API_KEY = os.environ.get("DOUBAO_API_KEY", "")

# ── COS 配置 (腾讯云对象存储) ──────────────────────────────
COS_BUCKET = "aigc-1319140468"
COS_REGION = "ap-beijing"
COS_CDN_BASE = "https://wy-static.vibeengine.com"


def _upload_to_cos(image_bytes: bytes, key: str, content_type: str = "image/png") -> str:
    """上传二进制图片到腾讯云 COS, 返回 CDN URL
    
    优先使用 qcloud_cos SDK, 如果没装则回退到 PUT 请求。
    """
    try:
        from qcloud_cos import CosConfig, CosS3Client
        config = CosConfig(
            Region=COS_REGION,
            SecretId=os.environ.get("SECRET_ID", ""),
            SecretKey=os.environ.get("SECRET_KEY", ""),
            Token=None,
            Scheme="https",
        )
        client = CosS3Client(config)
        response = client.put_object(
            Bucket=COS_BUCKET,
            Body=image_bytes,
            Key=key,
            ContentType=content_type,
            EnableMD5=False,
        )
        if "ETag" in response:
            url = f"{COS_CDN_BASE}/{key}"
            logger.info(f"[COS] Upload success: {url}")
            return url
        raise RuntimeError("COS upload failed: no ETag in response")
    except ImportError:
        logger.warning("[COS] qcloud_cos not installed, upload unavailable")
        raise RuntimeError(
            "COS SDK (qcloud_cos) not installed. "
            "Install it with: pip install cos-python-sdk-v5"
        )

# 图像生成 API — text2img 和 img2img 都走同一个 endpoint
DOUBAO_IMAGE_API_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"


def _get_headers() -> dict:
    """构建请求头"""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DOUBAO_API_KEY}",
    }


# ── 图片上传工具 ──────────────────────────────────────────

@tool
def upload_image(image_source: str) -> str:
    """Upload a user-provided image and return a publicly accessible URL.

    Accepts either:
    - A local file path (e.g. "/Users/me/photo.png", "./image.jpg")
    - A base64-encoded image string (with or without data URI prefix)
    - An existing HTTP(S) URL (will be validated and returned as-is)

    The image will be uploaded to cloud storage (COS) and a CDN URL is returned.
    This URL can then be passed to image_generation for img2img editing.

    Args:
        image_source: Local file path, base64 string, or existing URL of the image.
    """
    image_source = image_source.strip()

    # ── Case 1: 已经是 URL → 直接返回
    if image_source.startswith(("http://", "https://")):
        return f"Image URL (already accessible): {image_source}"

    # ── Case 2: base64 字符串
    if image_source.startswith("data:image/") or _looks_like_base64(image_source):
        try:
            # 去掉 data URI 前缀
            raw_b64 = image_source
            content_type = "image/png"
            if "base64," in raw_b64:
                header, raw_b64 = raw_b64.split("base64,", 1)
                if "image/jpeg" in header:
                    content_type = "image/jpeg"
                elif "image/webp" in header:
                    content_type = "image/webp"

            image_bytes = base64.b64decode(raw_b64)
            ext = content_type.split("/")[-1]
            key = f"aigc-online/user-upload/{uuid.uuid4()}.{ext}"
            url = _upload_to_cos(image_bytes, key, content_type)
            return f"Image uploaded successfully.\nImage URL: {url}"
        except Exception as e:
            logger.error(f"[upload_image] base64 decode/upload failed: {e}")
            return f"Error: Failed to process base64 image — {e}"

    # ── Case 3: 本地文件路径
    file_path = Path(image_source).expanduser().resolve()
    if not file_path.exists():
        return f"Error: File not found at '{file_path}'"
    if not file_path.is_file():
        return f"Error: '{file_path}' is not a file."

    suffix = file_path.suffix.lower()
    content_type_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }
    content_type = content_type_map.get(suffix, "image/png")

    try:
        image_bytes = file_path.read_bytes()
        ext = suffix.lstrip(".")
        key = f"aigc-online/user-upload/{uuid.uuid4()}.{ext}"
        url = _upload_to_cos(image_bytes, key, content_type)
        return f"Image uploaded successfully.\nImage URL: {url}"
    except Exception as e:
        logger.error(f"[upload_image] file upload failed: {e}")
        return f"Error: Failed to upload image — {e}"


def _looks_like_base64(s: str) -> bool:
    """粗略判断一个字符串是否像 base64 编码的图片"""
    if len(s) < 100:
        return False
    import re
    # base64 只包含 A-Za-z0-9+/= 和空白
    cleaned = re.sub(r'\s', '', s)
    return bool(re.match(r'^[A-Za-z0-9+/]+=*$', cleaned)) and len(cleaned) > 100


# ── 生图工具 ──────────────────────────────────────────────

@tool
def text2img(prompt: str, size: str = "1280x720") -> str:
    """Generate an image from text description using Doubao Seedream 3.0.

    Args:
        prompt: Detailed description of the image to generate.
        size: Image dimensions, e.g. "1280x720", "1024x1024", "720x1280". Default "1280x720".
    """
    if not DOUBAO_API_KEY:
        return "Error: DOUBAO_API_KEY not set in environment variables."

    payload = {
        "model": "doubao-seedream-4-0-250828",
        "prompt": prompt,
        "size": size,
        "response_format": "url",
        "n": 1,
    }

    try:
        logger.info(f"[text2img] Generating: {prompt[:80]}...")
        response = requests.post(
            DOUBAO_IMAGE_API_URL,
            headers=_get_headers(),
            json=payload,
            timeout=120,
        )
        if response.status_code == 200:
            data = response.json()
            images = data.get("data", [])
            if images:
                image_url = images[0].get("url", "")
                logger.info(f"[text2img] Success: {image_url}")
                return (
                    f"Image generated successfully.\n"
                    f"Image URL: {image_url}\n"
                    f"Prompt used: {prompt}"
                )
            return "Error: No image returned from API."
        else:
            error_msg = response.text[:200]
            logger.error(f"[text2img] API error {response.status_code}: {error_msg}")
            return f"Error: API returned status {response.status_code}: {error_msg}"
    except Exception as e:
        logger.error(f"[text2img] Exception: {e}")
        return f"Error: {str(e)}"


@tool
def img2img(prompt: str, image_url: str) -> str:
    """Modify an existing image based on text instructions using Doubao Seedream 3.0.

    Args:
        prompt: Text instructions describing the modifications to apply.
        image_url: URL of the source image to modify.
    """
    if not DOUBAO_API_KEY:
        return "Error: DOUBAO_API_KEY not set in environment variables."

    payload = {
        "model": "doubao-seedream-4-0-250828",
        "prompt": prompt,
        "image": image_url,          # img2img 用 "image" 参数传入源图
        "response_format": "url",
        "n": 1,
    }

    try:
        logger.info(f"[img2img] Editing: {prompt[:80]}...")
        response = requests.post(
            DOUBAO_IMAGE_API_URL,     # img2img 也走 /images/generations
            headers=_get_headers(),
            json=payload,
            timeout=120,
        )
        if response.status_code == 200:
            data = response.json()
            images = data.get("data", [])
            if images:
                result_url = images[0].get("url", "")
                logger.info(f"[img2img] Success: {result_url}")
                return (
                    f"Image modified successfully.\n"
                    f"Modified image URL: {result_url}\n"
                    f"Source image URL: {image_url}\n"
                    f"Prompt used: {prompt}"
                )
            return "Error: No image returned from API."
        else:
            error_msg = response.text[:200]
            logger.error(f"[img2img] API error {response.status_code}: {error_msg}")
            return f"Error: API returned status {response.status_code}: {error_msg}"
    except Exception as e:
        logger.error(f"[img2img] Exception: {e}")
        return f"Error: {str(e)}"


# ── 终止工具 ──────────────────────────────────────────────

@tool
def finish_image_generation(result_summary: str) -> str:
    """Signal completion of image generation task.

    This is a TERMINATING tool. Call it when you are satisfied with the
    generated image, or when max attempts have been reached.
    Include the final image URL in the result_summary.

    Args:
        result_summary: Final summary including the image URL and any notes.
    """
    return f"<done/>\n{result_summary}"
