"""Safe, parameterised ComfyUI workflow templates.

The public API intentionally accepts values, never node ids or input names.  A
template owns those implementation details, which keeps Quick Generate from
turning into an arbitrary workflow editing endpoint.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Literal

from backend.tools.contracts import ToolError


WorkflowKind = Literal["image", "video"]
_SCALAR_TYPES = {"string", "integer", "number", "boolean"}


@dataclass(frozen=True, slots=True)
class Binding:
    name: str
    node_id: str
    input_name: str
    value_type: Literal["string", "integer", "number", "boolean"]
    required: bool = False
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkflowTemplate:
    id: str
    title: str
    kind: WorkflowKind
    version: int
    workflow: dict[str, Any]
    bindings: tuple[Binding, ...]

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "version": self.version,
            "bindings": [
                {
                    "name": item.name,
                    "type": item.value_type,
                    "required": item.required,
                    "minimum": item.minimum,
                    "maximum": item.maximum,
                    "choices": list(item.choices),
                }
                for item in self.bindings
            ],
        }


def _image_workflow() -> dict[str, Any]:
    # Deliberately a conventional API workflow.  Installations may replace the
    # model name through their saved template, while the exposed controls stay
    # constrained to ordinary generation parameters.
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 28, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "FinCtrl", "images": ["6", 0]}},
    }


def _video_workflow() -> dict[str, Any]:
    # A generic AnimateDiff-style shape.  It is a template rather than a claim
    # that every ComfyUI installation ships these custom nodes.
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 768, "height": 512, "batch_size": 1}},
        "5": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 24, "cfg": 6.5, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "VHS_VideoCombine", "inputs": {"images": ["6", 0], "frame_rate": 8, "loop_count": 0, "filename_prefix": "FinCtrl", "format": "video/h264-mp4"}},
    }


DEFAULT_TEMPLATES: tuple[WorkflowTemplate, ...] = (
    WorkflowTemplate(
        id="image-basic", title="Изображение · базовый", kind="image", version=1, workflow=_image_workflow(),
        bindings=(
            Binding("prompt", "2", "text", "string", required=True), Binding("negative_prompt", "3", "text", "string"),
            Binding("width", "4", "width", "integer", minimum=256, maximum=2048), Binding("height", "4", "height", "integer", minimum=256, maximum=2048),
            Binding("seed", "5", "seed", "integer", minimum=0, maximum=2**63 - 1), Binding("steps", "5", "steps", "integer", minimum=1, maximum=150),
            Binding("guidance", "5", "cfg", "number", minimum=0, maximum=30),
        ),
    ),
    WorkflowTemplate(
        id="video-basic", title="Видео · совместимый шаблон", kind="video", version=1, workflow=_video_workflow(),
        bindings=(
            Binding("prompt", "2", "text", "string", required=True), Binding("negative_prompt", "3", "text", "string"),
            Binding("width", "4", "width", "integer", minimum=256, maximum=1536), Binding("height", "4", "height", "integer", minimum=256, maximum=1536),
            Binding("seed", "5", "seed", "integer", minimum=0, maximum=2**63 - 1), Binding("steps", "5", "steps", "integer", minimum=1, maximum=100),
            Binding("guidance", "5", "cfg", "number", minimum=0, maximum=30), Binding("fps", "7", "frame_rate", "integer", minimum=1, maximum=60),
        ),
    ),
)


class WorkflowCatalog:
    def __init__(self, templates: tuple[WorkflowTemplate, ...] = DEFAULT_TEMPLATES) -> None:
        self._templates = {template.id: template for template in templates}

    def list(self, kind: WorkflowKind | None = None) -> list[dict[str, Any]]:
        return [template.describe() for template in self._templates.values() if kind is None or template.kind == kind]

    def get(self, template_id: str) -> WorkflowTemplate:
        try:
            return self._templates[template_id]
        except KeyError as exc:
            raise ToolError("unknown_workflow_template", "Workflow template was not found") from exc

    def bind(self, template_id: str, values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        template = self.get(template_id)
        if not isinstance(values, dict):
            raise ToolError("invalid_workflow_values", "Workflow values must be an object")
        allowed = {binding.name for binding in template.bindings}
        unknown = set(values) - allowed
        if unknown:
            raise ToolError("invalid_workflow_values", f"Unsupported workflow parameter: {sorted(unknown)[0]}")
        result = copy.deepcopy(template.workflow)
        normalized: dict[str, Any] = {}
        for binding in template.bindings:
            present = binding.name in values
            if binding.required and not present:
                raise ToolError("invalid_workflow_values", f"Workflow parameter is required: {binding.name}")
            if not present:
                continue
            value = values[binding.name]
            if binding.value_type == "string":
                if not isinstance(value, str) or len(value) > 12_000:
                    raise ToolError("invalid_workflow_values", f"Invalid text value: {binding.name}")
            elif binding.value_type == "boolean":
                if not isinstance(value, bool):
                    raise ToolError("invalid_workflow_values", f"Invalid boolean value: {binding.name}")
            elif binding.value_type == "integer":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ToolError("invalid_workflow_values", f"Invalid whole number: {binding.name}")
            elif binding.value_type == "number":
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ToolError("invalid_workflow_values", f"Invalid number: {binding.name}")
                value = float(value)
            if binding.minimum is not None and value < binding.minimum or binding.maximum is not None and value > binding.maximum:
                raise ToolError("invalid_workflow_values", f"Workflow parameter is outside its allowed range: {binding.name}")
            if binding.choices and value not in binding.choices:
                raise ToolError("invalid_workflow_values", f"Workflow parameter is not an allowed choice: {binding.name}")
            node = result.get(binding.node_id)
            if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
                raise ToolError("invalid_workflow_template", "Workflow template binding does not target a node input")
            node["inputs"][binding.input_name] = value
            normalized[binding.name] = value
        # A hard size boundary prevents a poisoned saved template from being
        # smuggled into a job record.
        if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 256_000:
            raise ToolError("invalid_workflow_template", "Workflow template is too large")
        return result, {"template_id": template.id, "template_version": template.version, "values": normalized}
