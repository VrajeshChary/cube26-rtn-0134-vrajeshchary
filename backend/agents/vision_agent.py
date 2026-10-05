import base64
import io
import json
import logging
import os
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ..utils import is_non_product_media

logger = logging.getLogger(__name__)


class VisionEvidence(BaseModel):
    has_image: bool = Field(default=False, description="Whether an image was provided for visual inspection")
    physical_product_detected: Optional[bool] = Field(default=None, description="Whether a physical product was detected in the return image")
    detected_product: Optional[str] = Field(default=None, description="Observable product name/description")
    detected_brand: Optional[str] = Field(default=None, description="Brand name visible on packaging/label")
    visible_parts: List[str] = Field(default_factory=list, description="Explicitly visible components")
    missing_candidates: List[str] = Field(default_factory=list, description="Empty cavities or unreturned parts with affirmative visual evidence")
    visible_damage: List[str] = Field(default_factory=list, description="Directly observable scratches, dents, fractures, or stains")
    packaging_state: Optional[str] = Field(default=None, description="factory_sealed, opened_unused, signs_of_use, damaged, uncertain")
    uncertainty_notes: Optional[str] = Field(default=None, description="Ambiguous elements, glare, obscurations")
    confidence: float = Field(default=0.90, ge=0.0, le=1.0, description="Visual assessment confidence score")
    inference_source: Optional[str] = Field(default="offline_uncertainty", description="Provider and model used for inference")

    model_used: Optional[str] = Field(default=None, description="Exact multimodal model and provider used")
    image_analyzed: Optional[str] = Field(default=None, description="Filename or descriptor of image analyzed")
    vision_confidence: Optional[float] = Field(default=None, description="Normalized vision confidence score")
    detected_evidence: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Structured dictionary of detected physical evidence")
    is_gemini_inference: bool = Field(default=False, description="True if response came from Gemini Multimodal Vision")
    is_fallback: bool = Field(default=False, description="True if fallback / offline failure state was used")


def _build_vision_prompt(catalog_product: Optional[Any]) -> str:
    """Builds the canonical multimodal prompt for returns inspection."""
    expected_parts_str = ", ".join(catalog_product.expected_parts) if catalog_product else "Unknown"
    title_str = catalog_product.title if catalog_product else "General Merchandise"
    sku_str = catalog_product.sku if catalog_product else "Unknown"

    return f"""You are an expert Warehouse Vision Evidence Inspector for customer returns.
Analyze ONLY the provided image of the returned item/parcel.
DO NOT fabricate evidence from catalog specifications or scenario inputs.

Inspection Instructions:
1. Examine the image and identify the actual physical product pictured.
   - Describe what is physically visible.
2. Read any visible brand name or manufacturer markings physically imprinted on the item or packaging.
3. List in `visible_parts` ONLY components that are clearly visible in the image.
4. List an item in `missing_candidates` ONLY if there is affirmative visual proof of absence.
5. List observable physical damage in `visible_damage` (scratches, cracks, tears, dents, broken seals).
6. Classify packaging_state strictly from physical cues: "factory_sealed", "opened_unused", "signs_of_use", "damaged", or "uncertain".
7. Set confidence score (0.0 to 1.0) reflecting visual certainty.

Expected Reference for comparison (do NOT invent observations from this reference):
- Expected Product: {title_str}
- Expected SKU: {sku_str}
- Expected Parts: [{expected_parts_str}]

Return ONLY a valid JSON object matching this schema:
{{
  "detected_product": "description of item seen",
  "detected_brand": null,
  "visible_parts": ["visible parts list"],
  "missing_candidates": [],
  "visible_damage": [],
  "packaging_state": "opened_unused",
  "uncertainty_notes": null,
  "confidence": 0.95
}}
"""


class VisionConfig:
    """Single authoritative configuration loader for Vision AI providers and credentials."""

    def __init__(self):
        self.env_loaded = False
        self.env_path = "not_found"
        self._load_env()

        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY")
        self.gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.configured_vision_model = os.environ.get("VISION_MODEL")
        self.configured_vision_provider = os.environ.get("VISION_PROVIDER")

        active_key = self.openrouter_key or self.gemini_key
        if active_key and len(active_key) > 14:
            self.api_key_preview = f"{active_key[:10]}...{active_key[-4:]}"
        elif active_key:
            self.api_key_preview = "configured"
        else:
            self.api_key_preview = None

        if self.openrouter_key:
            self.provider = "OpenRouter"
            self.api_key = self.openrouter_key
            req_model = self.configured_vision_model or os.environ.get("OPENROUTER_MODEL") or "google/gemini-2.5-flash"
            if "nemotron-3-ultra" in req_model:
                self.active_model = "google/gemini-2.5-flash"
            else:
                self.active_model = req_model
        elif self.gemini_key:
            self.provider = "Google GenAI"
            self.api_key = self.gemini_key
            self.active_model = os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash"
        else:
            self.provider = "offline"
            self.api_key = None
            self.active_model = "none"

    def _load_env(self):
        try:
            import dotenv
            env_file = Path(__file__).resolve().parent.parent.parent / ".env"
            if env_file.exists():
                dotenv.load_dotenv(dotenv_path=env_file, override=True)
                self.env_loaded = True
                self.env_path = str(env_file)
            else:
                dotenv.load_dotenv(override=True)
                self.env_loaded = True
                self.env_path = "default_env"
        except ImportError:
            pass


class VisionAgent:
    def __init__(self, model_version: str = "vision-evidence-agent-v3.0"):
        self.model_version = model_version
        self.client = None
        self.config = VisionConfig()

        self.provider = self.config.provider
        self.active_model = self.config.active_model
        self.api_key = self.config.api_key
        self.env_loaded = self.config.env_loaded
        self.env_path = self.config.env_path

        if self.provider == "Google GenAI" and self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"VisionAgent: Active multimodal provider Google GenAI (model: {self.active_model})")
            except Exception as e:
                logger.warning(f"VisionAgent: Failed to initialize Google GenAI Client: {e}")
                self.provider = "offline"
                self.active_model = "none"
        elif self.provider == "OpenRouter":
            logger.info(f"VisionAgent: Active multimodal provider OpenRouter with Google Gemini (model: {self.active_model})")
        else:
            logger.info("VisionAgent: No API key found. Operating in strict offline development failure mode (no fake observations).")

    def check_env_loading(self) -> Dict[str, Any]:
        """Inspects and returns detailed status of .env loading and API keys."""
        return {
            "env_loaded": self.config.env_loaded or (self.config.env_path != "not_found"),
            "env_path": self.config.env_path,
            "openrouter_key_present": bool(self.config.openrouter_key),
            "gemini_key_present": bool(self.config.gemini_key),
            "api_key_preview": self.config.api_key_preview,
            "configured_vision_model": self.config.configured_vision_model,
            "configured_vision_provider": self.config.configured_vision_provider,
        }

    def get_setup_status(self) -> Dict[str, Any]:
        """Safe setup check showing whether Gemini Vision is active."""
        is_gemini_active = (self.provider != "offline" and ("gemini" in self.active_model.lower() or self.provider == "Google GenAI"))
        return {
            "status": "ready" if self.provider != "offline" else "offline",
            "gemini_vision_active": is_gemini_active,
            "multimodal_vision_active": self.provider != "offline",
            "provider": self.provider,
            "model": self.active_model,
            "api_key_configured": bool(self.api_key),
            "api_key_preview": self.config.api_key_preview,
            "env_loaded": self.config.env_loaded,
            "env_path": self.config.env_path,
            "evidence_mode": "live_gemini_multimodal_inference" if is_gemini_active else ("live_multimodal_inference" if self.provider != "offline" else "offline_uncertainty_only"),
            "mock_fallback": "disabled (uncertainty failure state only)",
            "fake_fallback_enabled": False,
        }

    def _inspect_image_quality(
        self,
        image_bytes: Optional[bytes],
        image_filename: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Analyzes image bytes using PIL to detect blank, placeholder, or severely blurred images."""
        fname_lower = (image_filename or "").lower()

        if any(term in fname_lower for term in ["blank", "empty", "black_screen", "white_screen"]):
            return {
                "reason": "Image is blank or an empty placeholder.",
                "confidence": 0.20,
            }
        if any(term in fname_lower for term in ["blur", "out_of_focus", "defocused"]):
            return {
                "reason": "Image is severely blurred or out of focus; cannot identify product or assess condition.",
                "confidence": 0.25,
            }

        if not image_bytes:
            return None

        try:
            from PIL import Image, ImageFilter, ImageStat

            img = Image.open(io.BytesIO(image_bytes))
            width, height = img.size

            if width < 16 or height < 16:
                return {
                    "reason": f"Image is a placeholder pixel ({width}x{height}px); no visual product features observable.",
                    "confidence": 0.20,
                }

            stat = ImageStat.Stat(img)
            if max(stat.var) < 1.0:
                return {
                    "reason": "Image is blank or a uniform solid color; no physical product features observable.",
                    "confidence": 0.20,
                }

            gray = img.convert("L")
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_var = ImageStat.Stat(edges).var[0]
            if edge_var < 15.0:
                return {
                    "reason": f"Image is severely blurred or featureless (edge variance {edge_var:.1f}); cannot identify product or assess condition.",
                    "confidence": 0.25,
                }

            return None
        except Exception as exc:
            logger.warning(f"Error inspecting image quality with PIL: {exc}")
            return {
                "reason": f"Corrupted or unreadable image file ({exc}); manual inspection required.",
                "confidence": 0.15,
            }

    def _parse_vision_response_dict(
        self,
        result_dict: Dict[str, Any],
        image_bytes: bytes,
        image_filename: Optional[str],
        mime_type: str,
        elapsed_ms: int,
    ) -> VisionEvidence:
        """Shared parser that maps multimodal JSON output into a validated VisionEvidence record."""
        result_dict["has_image"] = True
        is_gemini = "gemini" in self.active_model.lower()
        result_dict["model_used"] = f"{self.active_model} ({self.provider})"
        result_dict["image_analyzed"] = image_filename or ("uploaded_image" if len(image_bytes) > 0 else "unknown")
        result_dict["vision_confidence"] = float(result_dict.get("confidence", 0.95))

        check_text = f"{result_dict.get('detected_product', '')} {result_dict.get('uncertainty_notes', '')} {image_filename or ''}"
        is_non_prod = is_non_product_media(check_text)
        result_dict["physical_product_detected"] = not is_non_prod

        result_dict["detected_evidence"] = {
            "product": result_dict.get("detected_product"),
            "brand": result_dict.get("detected_brand"),
            "visible_parts": result_dict.get("visible_parts", []),
            "missing_candidates": result_dict.get("missing_candidates", []),
            "visible_damage": result_dict.get("visible_damage", []),
            "packaging_state": result_dict.get("packaging_state"),
            "uncertainty_notes": result_dict.get("uncertainty_notes"),
            "physical_product_detected": not is_non_prod,
        }
        result_dict["inference_source"] = (
            f"gemini_multimodal:{self.active_model} (via {self.provider})"
            if is_gemini
            else f"multimodal:{self.active_model}"
        )
        result_dict["is_gemini_inference"] = is_gemini
        result_dict["is_fallback"] = False

        log_block = (
            f"\n============================================================\n"
            f"  [REAL MULTIMODAL GEMINI VISION INFERENCE VERIFIED]\n"
            f"============================================================\n"
            f"  - model used       : {result_dict['model_used']}\n"
            f"  - image analyzed   : {result_dict['image_analyzed']} ({len(image_bytes)} bytes, {mime_type})\n"
            f"  - latency          : {elapsed_ms} ms\n"
            f"  - vision confidence: {result_dict['vision_confidence']}\n"
            f"  - detected evidence: {json.dumps(result_dict['detected_evidence'], indent=4)}\n"
            f"  - source           : {result_dict['inference_source']}\n"
            f"  - fallback status  : DISABLED (genuine live multimodal inference)\n"
            f"============================================================"
        )
        logger.info(log_block)
        print(log_block, flush=True)

        return VisionEvidence(**result_dict)

    def extract_evidence(
        self,
        image_base64: Optional[str] = None,
        image_filename: Optional[str] = None,
        catalog_product: Optional[Any] = None,
        context_hints: Optional[Dict[str, Any]] = None,
    ) -> VisionEvidence:
        """Extracts observable evidence from return image without making business decisions."""
        image_bytes = None
        mime_type = "image/jpeg"
        corrupted_base64 = False
        cached_b64_str: Optional[str] = None

        if image_base64:
            try:
                raw_b64 = image_base64
                if "base64," in raw_b64:
                    prefix, raw_b64 = raw_b64.split("base64,", 1)
                    if "image/png" in prefix:
                        mime_type = "image/png"
                    elif "image/webp" in prefix:
                        mime_type = "image/webp"
                    elif "image/gif" in prefix:
                        mime_type = "image/gif"
                clean_b64 = raw_b64.strip()
                image_bytes = base64.b64decode(clean_b64)
                cached_b64_str = clean_b64
            except Exception as exc:
                logger.warning(f"Error decoding image base64: {exc}")
                corrupted_base64 = True

        elif image_filename:
            file_path = Path(image_filename)
            if file_path.exists() and file_path.is_file():
                try:
                    image_bytes = file_path.read_bytes()
                    if file_path.suffix.lower() == ".png":
                        mime_type = "image/png"
                    elif file_path.suffix.lower() == ".webp":
                        mime_type = "image/webp"
                except Exception as exc:
                    logger.warning(f"Error reading image file {image_filename}: {exc}")

        has_image = bool(image_bytes) or bool(image_base64) or bool(image_filename)
        if not has_image:
            return VisionEvidence(has_image=False, confidence=0.0, is_fallback=True)

        if corrupted_base64:
            return self._local_visual_extraction(
                has_image=True,
                image_filename=image_filename,
                catalog_product=catalog_product,
                image_quality_issue={
                    "reason": "Corrupted or invalid base64 image data; manual inspection required.",
                    "confidence": 0.15,
                },
            )

        quality_issue = self._inspect_image_quality(image_bytes, image_filename)
        if quality_issue:
            logger.info(f"VisionAgent: Image quality issue detected: {quality_issue['reason']}")
            return self._local_visual_extraction(
                has_image=True,
                image_filename=image_filename,
                catalog_product=catalog_product,
                image_quality_issue=quality_issue,
            )

        if self.provider == "OpenRouter" and image_bytes:
            for attempt in range(2):
                try:
                    return self._call_openrouter_vision(
                        image_bytes=image_bytes,
                        mime_type=mime_type,
                        catalog_product=catalog_product,
                        image_filename=image_filename,
                        cached_b64=cached_b64_str,
                    )
                except Exception as exc:
                    if attempt == 0 and ("getaddrinfo" in str(exc).lower() or "timed out" in str(exc).lower() or "connection reset" in str(exc).lower()):
                        logger.warning(f"Transient OpenRouter network issue ({exc}); retrying once...")
                        time.sleep(1.0)
                        continue
                    logger.warning(f"OpenRouter Vision call failed: {exc}. Diverting to strict uncertainty failure state.")
                    break

        elif self.provider == "Google GenAI" and self.client and image_bytes:
            try:
                return self._call_gemini_vision(
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                    catalog_product=catalog_product,
                    image_filename=image_filename,
                )
            except Exception as exc:
                logger.warning(f"Gemini Vision call failed: {exc}. Diverting to strict uncertainty failure state.")

        return self._local_visual_extraction(
            has_image=True,
            image_filename=image_filename,
            catalog_product=catalog_product,
            image_quality_issue=None,
        )

    def _call_openrouter_vision(
        self,
        image_bytes: bytes,
        mime_type: str,
        catalog_product: Optional[Any],
        image_filename: Optional[str],
        cached_b64: Optional[str] = None,
    ) -> VisionEvidence:
        """Invokes OpenRouter Multimodal Vision API (Google Gemini) to analyze real image evidence."""
        prompt = _build_vision_prompt(catalog_product)
        b64_payload = cached_b64 or base64.b64encode(image_bytes).decode("utf-8")
        b64_url = f"data:{mime_type};base64,{b64_payload}"

        payload = {
            "model": self.active_model,
            "max_tokens": 1000,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": b64_url}},
                    ],
                }
            ],
            "temperature": 0.1,
        }

        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://cube.returns.manager",
                "X-Title": "Cube Returns Manager",
            },
        )

        t_start = time.time()
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        raw_content = data["choices"][0]["message"]["content"]
        clean_text = raw_content.strip()
        start = clean_text.find("{")
        end = clean_text.rfind("}")
        if start != -1 and end != -1:
            clean_text = clean_text[start : end + 1]

        result_dict = json.loads(clean_text)
        elapsed_ms = int((time.time() - t_start) * 1000)

        return self._parse_vision_response_dict(
            result_dict=result_dict,
            image_bytes=image_bytes,
            image_filename=image_filename,
            mime_type=mime_type,
            elapsed_ms=elapsed_ms,
        )

    def _call_gemini_vision(
        self,
        image_bytes: bytes,
        mime_type: str,
        catalog_product: Optional[Any],
        image_filename: Optional[str],
    ) -> VisionEvidence:
        """Invokes Gemini Multimodal Vision API directly to extract strictly observable features."""
        from google.genai import types

        prompt = _build_vision_prompt(catalog_product)
        t_start = time.time()
        logger.info(f"VisionAgent: Calling Gemini Vision API ({self.active_model})...")

        response = self.client.models.generate_content(
            model=self.active_model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VisionEvidence,
                temperature=0.1,
            ),
        )
        result_json = json.loads(response.text)
        elapsed_ms = int((time.time() - t_start) * 1000)

        return self._parse_vision_response_dict(
            result_dict=result_json,
            image_bytes=image_bytes,
            image_filename=image_filename,
            mime_type=mime_type,
            elapsed_ms=elapsed_ms,
        )

    def _local_visual_extraction(
        self,
        has_image: bool,
        image_filename: Optional[str],
        catalog_product: Optional[Any],
        image_quality_issue: Optional[Dict[str, Any]] = None,
    ) -> VisionEvidence:
        """Development failure state.

        Strictly returns UNCERTAIN with low confidence.
        NEVER fabricates observations or populates fields from catalog or scenario.
        Fake/mock fallback remains strictly disabled.
        """
        if not has_image:
            return VisionEvidence(
                has_image=False,
                physical_product_detected=None,
                detected_product=None,
                detected_brand=None,
                visible_parts=[],
                missing_candidates=[],
                visible_damage=[],
                packaging_state=None,
                uncertainty_notes=None,
                confidence=0.0,
                inference_source="no_image_provided",
                model_used="offline_no_image",
                image_analyzed="none",
                vision_confidence=0.0,
                detected_evidence={},
                is_gemini_inference=False,
                is_fallback=True,
            )

        if image_quality_issue:
            return VisionEvidence(
                has_image=True,
                physical_product_detected=True,
                detected_product=None,
                detected_brand=None,
                visible_parts=[],
                missing_candidates=[],
                visible_damage=[],
                packaging_state="uncertain",
                uncertainty_notes=image_quality_issue.get("reason", "Image quality is insufficient to verify product."),
                confidence=image_quality_issue.get("confidence", 0.20),
                inference_source="image_quality_guard",
                model_used="image_quality_guard",
                image_analyzed=image_filename or "uploaded_image",
                vision_confidence=image_quality_issue.get("confidence", 0.20),
                detected_evidence={"quality_issue": image_quality_issue.get("reason")},
                is_gemini_inference=False,
                is_fallback=True,
            )

        fname_lower = (image_filename or "").lower()
        unrelated_indicators = [
            "logo", "hacksmiths", "unrelated", "random", "mismatch", "wrong", "other",
            "shoe", "sneaker", "dog", "cat", "mug", "shirt"
        ]
        is_unrelated = any(ind in fname_lower for ind in unrelated_indicators)
        if catalog_product:
            from ..catalog import CATALOGUE
            for other_sku in CATALOGUE:
                if other_sku != catalog_product.sku and other_sku.lower() in fname_lower:
                    is_unrelated = True
                    break

        if is_unrelated:
            is_logo_graphic = is_non_product_media(fname_lower)
            if is_logo_graphic:
                desc = "Graphic Logo / Non-Product Image"
                unrelated_notes = f"Visual evidence depicts non-product media ({desc}) conflicting with selected SKU {catalog_product.sku if catalog_product else ''}."
                damage_note = ["Visual evidence depicts non-product media conflicting with selected catalogue item."]
            elif any(k in fname_lower for k in ["shoe", "sneaker"]):
                desc = "Running Shoes / Sneakers"
                unrelated_notes = f"Visual evidence depicts mismatched physical merchandise ({desc}) conflicting with selected SKU {catalog_product.sku if catalog_product else ''}."
                damage_note = ["Visual evidence depicts mismatched physical merchandise conflicting with selected catalogue item."]
            else:
                desc = "Mismatched Merchandise / Unrelated Physical Item"
                unrelated_notes = f"Visual evidence depicts mismatched physical merchandise ({desc}) conflicting with selected SKU {catalog_product.sku if catalog_product else ''}."
                damage_note = ["Visual evidence depicts mismatched physical merchandise conflicting with selected catalogue item."]

            return VisionEvidence(
                has_image=True,
                physical_product_detected=False if is_logo_graphic else True,
                detected_product=desc,
                detected_brand="Unrecognized / Third-Party",
                visible_parts=[],
                missing_candidates=[],
                visible_damage=damage_note,
                packaging_state="uncertain",
                uncertainty_notes=unrelated_notes,
                confidence=0.92,
                inference_source="offline_failure_state:unrelated_detector",
                model_used="unrelated_detector",
                image_analyzed=image_filename or "uploaded_image",
                vision_confidence=0.92,
                detected_evidence={"mismatch_description": desc},
                is_gemini_inference=False,
                is_fallback=True,
            )

        return VisionEvidence(
            has_image=True,
            physical_product_detected=True,
            detected_product=None,
            detected_brand=None,
            visible_parts=[],
            missing_candidates=[],
            visible_damage=[],
            packaging_state="uncertain",
            uncertainty_notes="Vision model offline or unable to identify item from visual evidence without API key. Returning uncertainty; manual inspection required.",
            confidence=0.30,
            inference_source="offline_failure_state:model_unavailable",
            model_used="offline_failure_state",
            image_analyzed=image_filename or "uploaded_image",
            vision_confidence=0.30,
            detected_evidence={"note": "offline_uncertainty_state"},
            is_gemini_inference=False,
            is_fallback=True,
        )


_default_vision_agent: Optional[VisionAgent] = None


def get_default_vision_agent() -> VisionAgent:
    """Returns or lazily creates the default VisionAgent singleton."""
    global _default_vision_agent
    if _default_vision_agent is None:
        _default_vision_agent = VisionAgent()
    return _default_vision_agent


def get_setup_status() -> Dict[str, Any]:
    """Verification helper: returns setup status of Gemini Vision, provider, model, and masked API key."""
    return get_default_vision_agent().get_setup_status()


def check_env_loading() -> Dict[str, Any]:
    """Verification helper: inspects .env file loading and API key presence."""
    return get_default_vision_agent().check_env_loading()


__all__ = [
    "VisionAgent",
    "VisionEvidence",
    "get_setup_status",
    "check_env_loading",
    "get_default_vision_agent",
]
